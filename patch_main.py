import sys

def main():
    with open("src/minerva/main.py", "r") as f:
        content = f.read()

    # 1. Add execution_queue
    content = content.replace(
        "self._data_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)",
        "self._data_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)\n        self._execution_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)\n        self._execution_task: asyncio.Task | None = None"
    )

    # 2. Add execution_queue to PaperTrader
    content = content.replace(
        "paper = PaperTrader(initial_balance=10000.0)",
        "paper = PaperTrader(initial_balance=10000.0, execution_queue=self._execution_queue)"
    )

    # 3. Add execution_queue to ExchangeGateway
    content = content.replace(
        "sandbox=self._settings.exchange_sandbox,\n                )",
        "sandbox=self._settings.exchange_sandbox,\n                    execution_queue=self._execution_queue,\n                )"
    )

    # 4. Start execution task
    content = content.replace(
        "self._running = True\n        log.info(\"minerva_started\", mode=self._settings.agent_mode)",
        "self._running = True\n        self._execution_task = asyncio.create_task(self._process_executions())\n        log.info(\"minerva_started\", mode=self._settings.agent_mode)"
    )

    # 5. Stop execution task
    content = content.replace(
        "self._running = False\n\n        # Stop feeds",
        "self._running = False\n        if self._execution_task:\n            self._execution_task.cancel()\n\n        # Stop feeds"
    )

    # 6. Replace execution part in _process_symbol
    old_exec_part = """        # 9. Execute order
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
            self._metrics.total_exposure.set(self._oms.get_total_exposure())"""

    new_exec_part = """        # 9. Execute order (async submit)
        await self._oms.submit_order(order)
        exchange_order_id = await gateway.submit_order(order)

        if not exchange_order_id:
            log.warning("order_execution_failed", order_id=order.id)
            if self._metrics:
                self._metrics.record_order(
                    symbol, order.side.value, "failed"
                )
            return

        # 10. Notifications & logging (Entry)
        if self._telegram:
            self._telegram.notify_trade_entry(
                symbol=symbol,
                side=order.side.value,
                amount=order.amount,
                price=current_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                reasoning=aggregated.reasoning,
            )

        # Log reasoning to Supabase (we do this on entry now)
        if self._supabase:
            await self._supabase.log_order(order.model_dump(mode="json"))
            await self._supabase.log_reasoning(
                symbol=symbol,
                action=aggregated.action.value,
                reasoning=aggregated.reasoning,
                signals=aggregated.technical_signals,
                confidence=aggregated.confidence,
            )

        # Clear decision since we acted
        self._decision_engine.clear_decision(symbol)

        # Metrics are updated when fills are processed in _process_executions
"""
    content = content.replace(old_exec_part, new_exec_part)

    # 7. Add _process_executions method
    process_exec_method = """
    async def _process_executions(self) -> None:
        \"\"\"Background task to process execution fills from the queue.\"\"\"
        log.info("execution_processor_started")
        while self._running:
            try:
                fill = await self._execution_queue.get()
                if fill is None:
                    continue

                if self._metrics:
                    self._metrics.record_order(fill.symbol, fill.side.value, "filled")

                trade_record = await self._oms.process_fill(fill)

                if trade_record:
                    if self._risk_engine:
                        self._risk_engine.update_pnl(trade_record.pnl)

                    if self._metrics:
                        self._metrics.record_trade(
                            fill.symbol, trade_record.side.value, trade_record.pnl
                        )
                        self._metrics.pnl_total.inc(trade_record.pnl)

                    if self._supabase:
                        await self._supabase.log_trade(trade_record.model_dump(mode="json"))

                    if self._telegram:
                        duration_s = trade_record.duration_seconds
                        if duration_s < 60:
                            dur_str = f"{duration_s}s"
                        elif duration_s < 3600:
                            dur_str = f"{duration_s // 60}m"
                        else:
                            dur_str = f"{duration_s // 3600}h {(duration_s % 3600) // 60}m"

                        self._telegram.notify_trade_exit(
                            symbol=fill.symbol,
                            side=trade_record.side.value,
                            pnl=trade_record.pnl,
                            pnl_pct=trade_record.pnl_pct,
                            entry_price=trade_record.entry_price,
                            exit_price=trade_record.exit_price,
                            duration_str=dur_str,
                        )

                    if self._rag and self._redis:
                        market_summary_data = await self._redis.get_market_summary(fill.symbol)
                        outcome = f"PnL: ${trade_record.pnl:+.2f} ({trade_record.pnl_pct:+.2f}%)"
                        await self._rag.remember(
                            symbol=fill.symbol,
                            signals={},
                            sentiment=0,
                            market_summary=market_summary_data,
                            action="CLOSE",
                            outcome=outcome,
                            pnl=trade_record.pnl,
                        )

                # Update metrics
                if self._metrics and self._oms:
                    self._metrics.open_positions.set(len(self._oms.get_all_positions()))
                    self._metrics.total_exposure.set(self._oms.get_total_exposure())

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("execution_processor_error", error=str(e))
                await asyncio.sleep(1)

    async def _check_daily_report(self) -> None:"""

    content = content.replace("    async def _check_daily_report(self) -> None:", process_exec_method)

    with open("src/minerva/main.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    main()
