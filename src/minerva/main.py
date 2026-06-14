"""
Minerva AI — Main Entry Point.

Asyncio event loop orchestrating all components:
Data ingestion → AI Brain → Execution Engine → Monitoring.

Supports both live and paper trading modes.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

from minerva.backtest.paper_trader import PaperTrader
from minerva.brain.decision import DecisionEngine
from minerva.brain.fast_path import FastPathEngine
from minerva.brain.rag import RAGMemory
from minerva.brain.slow_path import SlowPathController
from minerva.config import Settings, get_settings
from minerva.execution.exchange_gateway import ExchangeGateway
from minerva.execution.oms import OrderManagementSystem
from minerva.execution.risk_engine import RiskEngine
from minerva.execution.smart_router import SmartRouter
from minerva.ingestion.aggregator import DataAggregator
from minerva.ingestion.market_feed import MarketFeed
from minerva.ingestion.news_feed import NewsFeed
from minerva.ingestion.onchain_feed import OnChainFeed
from minerva.ingestion.social_feed import SocialFeed
from minerva.logger import get_logger, setup_logging
from minerva.memory.redis_store import RedisStore
from minerva.memory.supabase_store import SupabaseStore
from minerva.memory.vector_store import VectorStore
from minerva.models.config import AgentConfig, RiskConfig
from minerva.models.signals import TradeAction
from minerva.monitoring.health import HealthServer
from minerva.monitoring.metrics import MetricsCollector
from minerva.monitoring.telegram_bot import TelegramNotifier

log = get_logger(__name__)


class MinervaAgent:
    """
    Main Minerva AI Trading Agent.

    Orchestrates all components and runs the main trading loop.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._running = False

        # Core shared resources
        self._data_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._redis: RedisStore | None = None
        self._supabase: SupabaseStore | None = None
        self._vector_store: VectorStore | None = None

        # Data ingestion
        self._market_feeds: list[MarketFeed] = []
        self._onchain_feed: OnChainFeed | None = None
        self._news_feed: NewsFeed | None = None
        self._social_feed: SocialFeed | None = None
        self._aggregator: DataAggregator | None = None

        # AI Brain
        self._fast_path: FastPathEngine | None = None
        self._slow_path: SlowPathController | None = None
        self._rag: RAGMemory | None = None
        self._decision_engine: DecisionEngine | None = None

        # Execution
        self._oms: OrderManagementSystem | None = None
        self._risk_engine: RiskEngine | None = None
        self._gateways: dict[str, Any] = {}
        self._smart_router: SmartRouter | None = None

        # Monitoring
        self._metrics: MetricsCollector | None = None
        self._telegram: TelegramNotifier | None = None
        self._health: HealthServer | None = None

        # Config
        self._trading_pairs = settings.get_trading_pairs_list()
        self._exchanges = self._get_configured_exchanges()
        self._agent_config = self._build_agent_config()
        self._risk_config = self._build_risk_config()

    def _get_configured_exchanges(self) -> list[str]:
        """Get list of exchanges with configured credentials."""
        exchanges = []
        if self._settings.binance_api_key:
            exchanges.append("binance")
        if self._settings.bybit_api_key:
            exchanges.append("bybit")
        if self._settings.okx_api_key:
            exchanges.append("okx")
        if not exchanges:
            exchanges.append(self._settings.primary_exchange)
        return exchanges

    def _build_agent_config(self) -> AgentConfig:
        s = self._settings
        return AgentConfig(
            mode=s.agent_mode,
            loop_interval_seconds=s.agent_loop_interval,
            slow_path_enabled=bool(s.get_llm_config()),
            rag_enabled=s.has_pinecone(),
            onchain_enabled=s.has_onchain(),
            news_enabled=s.has_news(),
            social_enabled=s.has_social(),
            telegram_enabled=s.has_telegram(),
            metrics_enabled=bool(s.prometheus_pushgateway_url),
        )

    def _build_risk_config(self) -> RiskConfig:
        s = self._settings
        return RiskConfig(
            max_position_size_usd=s.max_position_size_usd,
            max_total_exposure_usd=s.max_total_exposure_usd,
            max_drawdown_percent=s.max_drawdown_percent,
            daily_loss_limit_usd=s.daily_loss_limit_usd,
            token_whitelist=self._trading_pairs,
        )

    async def start(self) -> None:
        """Initialize all components and start the agent."""
        log.info(
            "minerva_starting",
            mode=self._settings.agent_mode,
            pairs=self._trading_pairs,
            exchanges=self._exchanges,
        )

        # --- Initialize core services ---

        # Redis
        self._redis = RedisStore(self._settings.redis_url)
        await self._redis.connect()

        # Supabase
        if self._settings.has_supabase():
            self._supabase = SupabaseStore(
                self._settings.supabase_url,
                self._settings.supabase_key,
            )
            await self._supabase.connect()

        # Pinecone
        if self._settings.has_pinecone():
            self._vector_store = VectorStore(
                self._settings.pinecone_api_key,
                self._settings.pinecone_index_name,
            )
            await self._vector_store.connect()

        # --- Data Ingestion ---
        self._aggregator = DataAggregator(self._data_queue, self._redis)
        await self._aggregator.start()

        # Market feeds for each exchange
        for exchange_id in self._exchanges:
            creds = self._settings.get_exchange_credentials(exchange_id)
            feed = MarketFeed(
                exchange_id=exchange_id,
                credentials=creds,
                symbols=self._trading_pairs,
                data_queue=self._data_queue,
                timeframes=["1m", "5m", "1h"],
            )
            self._market_feeds.append(feed)
            await feed.start()

        # Optional feeds
        if self._agent_config.onchain_enabled:
            self._onchain_feed = OnChainFeed(
                ws_url=self._settings.alchemy_ws_url,
                data_queue=self._data_queue,
                whale_threshold_eth=self._settings.whale_transfer_threshold_eth,
            )
            await self._onchain_feed.start()

        if self._agent_config.news_enabled:
            currencies = [p.split("/")[0] for p in self._trading_pairs]
            self._news_feed = NewsFeed(
                api_key=self._settings.cryptopanic_api_key,
                data_queue=self._data_queue,
                currencies=currencies,
            )
            await self._news_feed.start()

        if self._agent_config.social_enabled:
            self._social_feed = SocialFeed(
                bearer_token=self._settings.twitter_bearer_token,
                data_queue=self._data_queue,
            )
            await self._social_feed.start()

        # --- AI Brain ---
        self._fast_path = FastPathEngine()

        llm_config = self._settings.get_llm_config()
        if llm_config and self._agent_config.slow_path_enabled:
            self._slow_path = SlowPathController(
                api_key=llm_config["api_key"],
                model=llm_config["model"],
                base_url=llm_config.get("base_url"),
                timeout=self._settings.llm_timeout,
            )

        if self._vector_store and self._agent_config.rag_enabled:
            self._rag = RAGMemory(self._vector_store)

        self._decision_engine = DecisionEngine(
            fast_weight=self._agent_config.fast_path_weight,
            slow_weight=self._agent_config.slow_path_weight,
            buy_threshold=self._agent_config.buy_threshold,
            sell_threshold=self._agent_config.sell_threshold,
            min_confidence=self._risk_config.min_signal_confidence,
        )

        # --- Execution ---
        self._risk_engine = RiskEngine(self._risk_config)
        self._oms = OrderManagementSystem(self._redis)
        await self._oms.initialize()

        # Exchange gateways
        is_paper = self._settings.agent_mode == "paper"
        if is_paper:
            paper = PaperTrader(initial_balance=10000.0)
            await paper.connect()
            for exchange_id in self._exchanges:
                self._gateways[exchange_id] = paper
        else:
            for exchange_id in self._exchanges:
                gw = ExchangeGateway(
                    exchange_id=exchange_id,
                    credentials=self._settings.get_exchange_credentials(exchange_id),
                    sandbox=False,
                )
                await gw.connect()
                self._gateways[exchange_id] = gw

        self._smart_router = SmartRouter(self._redis, self._exchanges)

        # Initialize risk engine equity
        primary = self._gateways.get(self._settings.primary_exchange) or next(
            iter(self._gateways.values()), None
        )
        if primary:
            balance = await primary.get_balance("USDT")
            self._risk_engine.set_initial_equity(balance)

        # --- Monitoring ---
        self._health = HealthServer()
        await self._health.start()

        self._metrics = MetricsCollector(self._settings.prometheus_pushgateway_url)
        if self._agent_config.metrics_enabled:
            await self._metrics.start_push_loop()

        if self._agent_config.telegram_enabled:
            self._telegram = TelegramNotifier(
                self._settings.telegram_bot_token,
                self._settings.telegram_chat_id,
            )
            await self._telegram.start()
            self._telegram.notify_startup(
                self._settings.agent_mode, self._trading_pairs
            )

        # Update health
        self._health.update_component("redis", await self._redis.health_check())
        self._health.update_component("exchange", True)
        self._health.update_status("running")

        self._running = True
        log.info("minerva_started", mode=self._settings.agent_mode)

    async def run_loop(self) -> None:
        """Main agent trading loop."""
        loop_interval = self._agent_config.loop_interval_seconds

        while self._running:
            loop_start = time.monotonic()

            try:
                await self._agent_iteration()

                if self._health:
                    self._health.update_loop()

            except Exception as e:
                log.error("agent_loop_error", error=str(e))
                if self._metrics:
                    self._metrics.record_error("agent_loop", type(e).__name__)
                if self._telegram:
                    self._telegram.notify_error("agent_loop", str(e))

            # Wait for next iteration
            elapsed = time.monotonic() - loop_start
            if self._metrics:
                self._metrics.loop_duration.observe(elapsed)

            sleep_time = max(0, loop_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _agent_iteration(self) -> None:
        """Single iteration of the agent trading loop."""
        for symbol in self._trading_pairs:
            try:
                await self._process_symbol(symbol)
            except Exception as e:
                log.error("symbol_processing_error", symbol=symbol, error=str(e))

    async def _process_symbol(self, symbol: str) -> None:
        """Process a single trading pair through the full pipeline."""
        primary_exchange = self._settings.primary_exchange

        # 1. Get market data from aggregator
        ohlcv_history = self._aggregator.get_ohlcv_history(
            symbol, primary_exchange, "1m", limit=200
        )
        market_summary_data = await self._redis.get_market_summary(symbol)

        if not ohlcv_history:
            return  # No data yet

        # Get order book imbalance
        ob = self._aggregator.get_orderbook(symbol, primary_exchange)
        ob_imbalance = ob.imbalance if ob else 0.0

        # 2. Fast path signal
        fast_signal = self._fast_path.compute_signal(
            symbol=symbol,
            ohlcv_history=ohlcv_history,
            orderbook_imbalance=ob_imbalance,
            timeframe="1m",
        )

        if self._metrics:
            self._metrics.record_signal(
                symbol, fast_signal.source.value, "computed"
            )

        # 3. Slow path (LLM) — only if enabled and available
        llm_decision = None
        if self._slow_path and self._agent_config.slow_path_enabled:
            # Get RAG experiences
            past_experiences = []
            if self._rag:
                past_experiences = await self._rag.recall(
                    symbol=symbol,
                    signals=fast_signal.metadata,
                    sentiment=self._aggregator.get_sentiment(symbol),
                    market_summary=market_summary_data,
                )

            # Get current positions for context
            positions_list = [
                pos.model_dump(mode="json")
                for pos in self._oms.get_all_positions().values()
            ]

            llm_decision = await self._slow_path.analyze(
                symbol=symbol,
                market_summary=market_summary_data,
                signals=fast_signal.metadata,
                sentiment_score=self._aggregator.get_sentiment(symbol),
                news_items=self._aggregator.get_recent_news(),
                onchain_events=self._aggregator.get_onchain_events(),
                current_positions=positions_list,
                past_experiences=past_experiences,
                risk_config=self._risk_config.model_dump(),
            )

        # 4. Decision engine — aggregate signals
        has_position = self._oms.has_position(symbol)
        aggregated = self._decision_engine.make_decision(
            symbol=symbol,
            fast_signal=fast_signal,
            llm_decision=llm_decision,
            sentiment_score=self._aggregator.get_sentiment(symbol),
            has_open_position=has_position,
        )

        if aggregated is None or aggregated.action == TradeAction.HOLD:
            return  # No action needed

        # 5. Select best exchange
        best_exchange = await self._smart_router.find_best_venue(
            symbol, aggregated.action.value
        )
        if not best_exchange:
            best_exchange = primary_exchange

        gateway = self._gateways.get(best_exchange)
        if not gateway:
            return

        # 6. Get current price and balance
        balance = await gateway.get_balance("USDT")
        ticker = await gateway.get_ticker(symbol)
        current_price = ticker.get("last", 0) if ticker else 0

        if current_price <= 0:
            return

        # Update paper trader price if in paper mode
        if isinstance(gateway, PaperTrader):
            gateway.set_price(symbol, current_price)

        # 7. Create order
        order = self._oms.create_order_from_signal(
            signal=aggregated,
            exchange=best_exchange,
            current_price=current_price,
            available_balance=balance,
        )

        if order is None:
            return

        # 8. Risk validation
        positions = {
            sym: pos for sym, pos in self._oms.get_all_positions().items()
        }
        violations = self._risk_engine.validate_order(
            order=order,
            current_positions=positions,
            current_price=current_price,
            available_balance=balance,
        )

        if violations:
            if self._risk_engine.is_trading_halted and self._telegram:
                risk_status = self._risk_engine.get_risk_status()
                self._telegram.notify_circuit_breaker(
                    risk_status["drawdown_pct"],
                    risk_status["daily_pnl"],
                )
            return

        # 9. Execute order
        await self._oms.submit_order(order)
        fill = await gateway.submit_order(order)

        if fill is None:
            log.warning("order_execution_failed", order_id=order.id)
            if self._metrics:
                self._metrics.record_order(
                    symbol, order.side.value, "failed"
                )
            return

        if self._metrics:
            self._metrics.record_order(symbol, order.side.value, "filled")

        # 10. Process fill
        trade_record = await self._oms.process_fill(fill)

        # 11. Notifications & logging
        if self._telegram:
            self._telegram.notify_trade_entry(
                symbol=symbol,
                side=order.side.value,
                amount=fill.amount,
                price=fill.price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                reasoning=aggregated.reasoning,
            )

        # 12. Handle completed trade
        if trade_record:
            self._risk_engine.update_pnl(trade_record.pnl)

            if self._metrics:
                self._metrics.record_trade(
                    symbol, trade_record.side.value, trade_record.pnl
                )
                self._metrics.pnl_total.inc(trade_record.pnl)

            if self._supabase:
                await self._supabase.log_trade(trade_record.model_dump(mode="json"))
                await self._supabase.log_reasoning(
                    symbol=symbol,
                    action=aggregated.action.value,
                    reasoning=aggregated.reasoning,
                    signals=aggregated.technical_signals,
                    confidence=aggregated.confidence,
                )

            if self._telegram:
                duration_s = trade_record.duration_seconds
                if duration_s < 60:
                    dur_str = f"{duration_s}s"
                elif duration_s < 3600:
                    dur_str = f"{duration_s // 60}m"
                else:
                    dur_str = f"{duration_s // 3600}h {(duration_s % 3600) // 60}m"

                self._telegram.notify_trade_exit(
                    symbol=symbol,
                    side=trade_record.side.value,
                    pnl=trade_record.pnl,
                    pnl_pct=trade_record.pnl_pct,
                    entry_price=trade_record.entry_price,
                    exit_price=trade_record.exit_price,
                    duration_str=dur_str,
                )

            # Store experience in RAG
            if self._rag:
                outcome = f"PnL: ${trade_record.pnl:+.2f} ({trade_record.pnl_pct:+.2f}%)"
                await self._rag.remember(
                    symbol=symbol,
                    signals=aggregated.technical_signals,
                    sentiment=aggregated.sentiment_score or 0,
                    market_summary=market_summary_data,
                    action=aggregated.action.value,
                    outcome=outcome,
                    pnl=trade_record.pnl,
                )

            self._decision_engine.clear_decision(symbol)

        # Log order to Supabase
        if self._supabase:
            await self._supabase.log_order(order.model_dump(mode="json"))

        # Update metrics
        if self._metrics:
            self._metrics.open_positions.set(
                len(self._oms.get_all_positions())
            )
            self._metrics.total_exposure.set(self._oms.get_total_exposure())

    async def stop(self) -> None:
        """Gracefully shut down all components."""
        log.info("minerva_stopping")
        self._running = False

        # Stop feeds
        for feed in self._market_feeds:
            await feed.stop()
        if self._onchain_feed:
            await self._onchain_feed.stop()
        if self._news_feed:
            await self._news_feed.stop()
        if self._social_feed:
            await self._social_feed.stop()
        if self._aggregator:
            await self._aggregator.stop()

        # Stop monitoring
        if self._telegram:
            await self._telegram.stop()
        if self._metrics:
            await self._metrics.stop()
        if self._health:
            await self._health.stop()

        # Close gateways
        closed = set()
        for gw in self._gateways.values():
            gw_id = id(gw)
            if gw_id not in closed:
                await gw.disconnect()
                closed.add(gw_id)

        # Close stores
        if self._vector_store:
            await self._vector_store.disconnect()
        if self._supabase:
            await self._supabase.disconnect()
        if self._redis:
            await self._redis.disconnect()

        log.info("minerva_stopped")


async def _run_agent() -> None:
    """Initialize and run the agent."""
    settings = get_settings()
    setup_logging(settings.log_level)

    agent = MinervaAgent(settings)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("shutdown_signal_received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await agent.start()

        # Run main loop until shutdown signal
        loop_task = asyncio.create_task(agent.run_loop())

        await shutdown_event.wait()

        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        log.error("agent_fatal_error", error=str(e))
    finally:
        await agent.stop()


def main() -> None:
    """Entry point for the Minerva AI trading agent."""
    try:
        asyncio.run(_run_agent())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
