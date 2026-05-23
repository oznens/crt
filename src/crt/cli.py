"""Entry-point: `crt` command."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from crt.backtest.engine import BacktestRunner, format_report
from crt.context import Tier
from crt.data.mexc import MexcClient
from crt.models import Timeframe
from crt.paper import PaperConfig, PaperEngine
from crt.runtime import Runtime

DEFAULT_TFS = [Timeframe.M15, Timeframe.H1, Timeframe.H4]


def _shared_universe_args(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--symbols", "-s", nargs="+",
        help="Explicit symbol list, e.g. BTC_USDT ETH_USDT",
    )
    g.add_argument(
        "--top", "-n", type=int, default=50,
        help="Auto-discover the top N USDT-perp symbols by 24h volume (default 50)",
    )
    p.add_argument(
        "--tf", "-t", nargs="+", default=[t.value for t in DEFAULT_TFS],
        help="Timeframes (1m,5m,15m,1h,4h,1d,1w)",
    )
    p.add_argument("--quote", default="USDT", help="Quote asset filter for --top")
    p.add_argument(
        "--min-tier", choices=[t.value for t in Tier], default=Tier.MEDIUM.value,
        help="Reject candles below this time-window tier (default: medium)",
    )
    p.add_argument(
        "--strict-htf", action="store_true",
        help="Require parent HTF candle bias to agree with signal direction",
    )
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--risk", type=float, default=100.0, help="USD risked per trade")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="crt", description="CRT scanner + paper trading terminal")
    p.add_argument("--log", default="INFO")
    sub = p.add_subparsers(dest="cmd", required=False)

    p_scan = sub.add_parser("scan", help="Live scanner + paper trading TUI (default)")
    _shared_universe_args(p_scan)

    p_bt = sub.add_parser("backtest", help="Replay historical candles through the pipeline")
    _shared_universe_args(p_bt)
    p_bt.add_argument(
        "--bars", type=int, default=500,
        help="Closed candles per (symbol, tf) to pull from REST (default 500)",
    )

    # Default to `scan` if no subcommand given so old usage keeps working.
    args = p.parse_args(argv)
    if args.cmd is None:
        args = p.parse_args(["scan"] + (argv if argv is not None else sys.argv[1:]))
    return args


async def _resolve_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return args.symbols
    async with MexcClient() as client:
        return await client.fetch_top_symbols(limit=args.top, quote=args.quote)


async def _run_scan(args: argparse.Namespace) -> int:
    symbols = await _resolve_symbols(args)
    logging.info("Scanning %d symbols: %s%s",
                 len(symbols), ", ".join(symbols[:8]),
                 ("..." if len(symbols) > 8 else ""))
    timeframes = [Timeframe(t) for t in args.tf]
    engine = PaperEngine(PaperConfig(starting_balance=args.balance, risk_per_trade=args.risk))
    runtime = Runtime(
        symbols=symbols, timeframes=timeframes, engine=engine,
        min_tier=Tier(args.min_tier),
        require_htf_alignment=args.strict_htf,
    )
    try:
        await runtime.run()
    except KeyboardInterrupt:
        pass
    return 0


async def _run_backtest(args: argparse.Namespace) -> int:
    symbols = await _resolve_symbols(args)
    timeframes = [Timeframe(t) for t in args.tf]
    logging.info("Backtesting %d symbols × %d tfs × %d bars",
                 len(symbols), len(timeframes), args.bars)
    runner = BacktestRunner(
        symbols=symbols, timeframes=timeframes,
        paper_config=PaperConfig(starting_balance=args.balance, risk_per_trade=args.risk),
        min_tier=Tier(args.min_tier),
        require_htf_alignment=args.strict_htf,
    )
    async with MexcClient() as client:
        await runner.load_from_mexc(client, limit_per_tf=args.bars)
    print(format_report(runner.report()))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
    )
    try:
        if args.cmd == "backtest":
            return asyncio.run(_run_backtest(args))
        return asyncio.run(_run_scan(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
