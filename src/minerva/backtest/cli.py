"""
Minerva AI — Backtest CLI.

Command-line interface for running historical backtests.
Usage: minerva-backtest --symbol BTC/USDT --timeframe 1h --limit 1000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

from minerva.backtest.runner import BacktestRunner
from minerva.config import get_settings
from minerva.logger import get_logger, setup_logging

log = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for backtest."""
    parser = argparse.ArgumentParser(
        prog="minerva-backtest",
        description="Run historical backtests for Minerva AI trading signals.",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        choices=["binance", "bybit", "okx"],
        help="Exchange to fetch data from (default: binance)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        help="Candle timeframe (default: 1h)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Number of candles to fetch (default: 1000)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10000.0,
        help="Initial balance in USDT (default: 10000)",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=0.001,
        help="Fee rate per trade (default: 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--buy-threshold",
        type=float,
        default=0.3,
        help="Buy signal threshold (default: 0.3)",
    )
    parser.add_argument(
        "--sell-threshold",
        type=float,
        default=-0.3,
        help="Sell signal threshold (default: -0.3)",
    )
    parser.add_argument(
        "--position-size",
        type=float,
        default=10.0,
        help="Position size as %% of balance (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output JSON file path for results (default: print to stdout)",
    )
    parser.add_argument(
        "--save-supabase",
        action="store_true",
        help="Persist results to Supabase (requires SUPABASE_URL/KEY)",
    )
    return parser.parse_args()


async def _run_backtest(args: argparse.Namespace) -> dict:
    """Execute the backtest with parsed arguments."""
    runner = BacktestRunner(
        initial_balance=args.balance,
        fee_rate=args.fee,
    )

    log.info(
        "fetching_historical_data",
        symbol=args.symbol,
        exchange=args.exchange,
        timeframe=args.timeframe,
        limit=args.limit,
    )

    data = await runner.fetch_historical_data(
        symbol=args.symbol,
        exchange_id=args.exchange,
        timeframe=args.timeframe,
        limit=args.limit,
    )

    log.info(
        "data_fetched",
        candles=len(data),
        start=str(data.iloc[0]["timestamp"]) if len(data) > 0 else "N/A",
        end=str(data.iloc[-1]["timestamp"]) if len(data) > 0 else "N/A",
    )

    result = await runner.run(
        symbol=args.symbol,
        data=data,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        position_size_pct=args.position_size,
        timeframe=args.timeframe,
    )

    return result


async def _save_to_supabase(result: dict) -> None:
    """Persist backtest results to Supabase."""
    settings = get_settings()
    if not settings.has_supabase():
        log.warning("supabase_not_configured", message="Skipping Supabase save")
        return

    from minerva.memory.supabase_store import SupabaseStore

    store = SupabaseStore(settings.supabase_url, settings.supabase_key)
    await store.connect()

    try:
        # Prepare a summary (omit full trades list for storage)
        summary = {k: v for k, v in result.items() if k != "trades"}
        summary["run_timestamp"] = datetime.now(tz=timezone.utc).isoformat()
        summary["trade_count"] = len(result.get("trades", []))
        await store.log_backtest_result(summary)
        log.info("backtest_saved_to_supabase")
    except Exception as e:
        log.warning("supabase_save_error", error=str(e))
    finally:
        await store.disconnect()


def _print_summary(result: dict) -> None:
    """Print formatted backtest summary to stdout."""
    print("\n" + "=" * 60)
    print("  MINERVA AI — Backtest Results")
    print("=" * 60)
    print(f"  Symbol:          {result['symbol']}")
    print(f"  Timeframe:       {result['timeframe']}")
    print(f"  Period:          {result.get('period_start', 'N/A')}")
    print(f"                   → {result.get('period_end', 'N/A')}")
    print(f"  Candles:         {result['candles']}")
    print("-" * 60)
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Winning:         {result['winning_trades']}")
    print(f"  Losing:          {result['losing_trades']}")
    print(f"  Win Rate:        {result['win_rate']:.1f}%")
    print("-" * 60)
    pnl = result["total_pnl"]
    pnl_sign = "+" if pnl >= 0 else ""
    print(f"  Total PnL:       {pnl_sign}${pnl:,.2f} ({pnl_sign}{result['pnl_pct']:.2f}%)")
    print(f"  Final Balance:   ${result['final_balance']:,.2f}")
    print(f"  Total Fees:      ${result['total_fees']:,.4f}")
    avg_win = result.get("avg_win", 0)
    avg_loss = result.get("avg_loss", 0)
    print(f"  Avg Win:         ${avg_win:,.4f}")
    print(f"  Avg Loss:        ${avg_loss:,.4f}")
    print("=" * 60 + "\n")


def main() -> None:
    """Entry point for minerva-backtest CLI."""
    args = _parse_args()
    setup_logging("INFO")

    try:
        result = asyncio.run(_run_backtest(args))
    except KeyboardInterrupt:
        print("\nBacktest cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\nBacktest failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Print human-readable summary
    _print_summary(result)

    # Save to file if requested
    if args.output:
        # Remove non-serializable items for JSON output
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Results saved to: {args.output}")

    # Save to Supabase if requested
    if args.save_supabase:
        try:
            asyncio.run(_save_to_supabase(result))
        except Exception as e:
            print(f"Supabase save failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
