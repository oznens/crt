"""Entry-point: `crt` command."""

from __future__ import annotations

import argparse
import asyncio
import logging

from crt.models import Timeframe
from crt.paper import PaperConfig, PaperEngine
from crt.runtime import Runtime

DEFAULT_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
DEFAULT_TFS = [Timeframe.M15, Timeframe.H1, Timeframe.H4]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="crt", description="CRT scanner + paper trading terminal")
    p.add_argument(
        "--symbols", "-s", nargs="+", default=DEFAULT_SYMBOLS,
        help="MEXC futures symbols, e.g. BTC_USDT ETH_USDT",
    )
    p.add_argument(
        "--tf", "-t", nargs="+", default=[t.value for t in DEFAULT_TFS],
        help="Timeframes (1m,5m,15m,1h,4h,1d,1w)",
    )
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--risk", type=float, default=100.0, help="USD risked per trade")
    p.add_argument("--log", default="INFO")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
    )
    timeframes = [Timeframe(t) for t in args.tf]
    engine = PaperEngine(PaperConfig(starting_balance=args.balance, risk_per_trade=args.risk))
    runtime = Runtime(symbols=args.symbols, timeframes=timeframes, engine=engine)
    try:
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
