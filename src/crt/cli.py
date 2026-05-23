"""Entry-point: `crt` command."""

from __future__ import annotations

import argparse
import asyncio
import logging

from crt.data.mexc import MexcClient
from crt.models import Timeframe
from crt.paper import PaperConfig, PaperEngine
from crt.runtime import Runtime

DEFAULT_TFS = [Timeframe.M15, Timeframe.H1, Timeframe.H4]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="crt", description="CRT scanner + paper trading terminal")
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
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--risk", type=float, default=100.0, help="USD risked per trade")
    p.add_argument("--log", default="INFO")
    return p.parse_args(argv)


async def _resolve_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return args.symbols
    async with MexcClient() as client:
        return await client.fetch_top_symbols(limit=args.top, quote=args.quote)


async def _async_main(args: argparse.Namespace) -> int:
    symbols = await _resolve_symbols(args)
    logging.info("Scanning %d symbols: %s%s",
                 len(symbols), ", ".join(symbols[:8]),
                 ("..." if len(symbols) > 8 else ""))
    timeframes = [Timeframe(t) for t in args.tf]
    engine = PaperEngine(PaperConfig(starting_balance=args.balance, risk_per_trade=args.risk))
    runtime = Runtime(symbols=symbols, timeframes=timeframes, engine=engine)
    try:
        await runtime.run()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
    )
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
