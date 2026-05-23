"""Entry-point: `crt` command."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from pathlib import Path

from crt.backtest.engine import BacktestRunner, format_report
from crt.chart import write_chart_html
from crt.context import SMTMonitor, Tier, score_signal
from crt.data.mexc import MexcClient
from crt.detector import CRTDetector, detect_kod, detect_model1, model1_to_signal
from crt.models import Direction, Timeframe
from crt.paper import PaperConfig, PaperEngine
from crt.runtime import Runtime
from crt.smc import compute as compute_smc
from crt.store import CandleStore

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
    p.add_argument(
        "--min-confluence", type=float, default=-1e9,
        help="Drop signals with a confluence score below this threshold (default: no floor)",
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

    p_chart = sub.add_parser(
        "chart",
        help="Render a candle chart with SMC + CRT overlays to an HTML file",
    )
    p_chart.add_argument("symbol", help="Single symbol, e.g. BTC_USDT")
    p_chart.add_argument(
        "--tf", default=Timeframe.H1.value,
        help="Timeframe (default 1h)",
    )
    p_chart.add_argument(
        "--bars", type=int, default=500,
        help="Closed candles to fetch (default 500)",
    )
    p_chart.add_argument(
        "--out", default="chart.html",
        help="Output HTML file path (default chart.html)",
    )
    p_chart.add_argument(
        "--refresh", type=int, default=0,
        help="Add meta-refresh tag with given seconds; 0 disables auto-reload",
    )
    p_chart.add_argument(
        "--watch", type=int, default=0,
        help="Re-render every N seconds and rewrite the same file (0 = one-shot)",
    )
    p_chart.add_argument("--swing-length", type=int, default=10)

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
        min_confluence=args.min_confluence,
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
        min_confluence=args.min_confluence,
    )
    async with MexcClient() as client:
        await runner.load_from_mexc(client, limit_per_tf=args.bars)
    print(format_report(runner.report()))
    return 0


async def _run_chart_once(args: argparse.Namespace) -> int:
    tf = Timeframe(args.tf)
    out = Path(args.out)
    async with MexcClient() as client:
        candles = await client.fetch_klines(args.symbol, tf, limit=args.bars)
        # Pair candles for SMT divergence overlay.
        smt_monitor = SMTMonitor(CandleStore())
        pair = smt_monitor.pair_for(args.symbol)
        pair_candles: list = []
        if pair is not None:
            try:
                pair_candles = await client.fetch_klines(pair, tf, limit=args.bars)
            except Exception:
                pair_candles = []
    store = CandleStore()
    for c in candles:
        store.append(c)
    for c in pair_candles:
        store.append(c)

    # CRT subtype signals + Model #1 signals, both scored by confluence.
    signals = list(CRTDetector(store).evaluate(args.symbol, tf))
    for m1 in detect_model1(candles):
        signals.append(model1_to_signal(m1))
    snap = compute_smc(candles)
    smt = SMTMonitor(store)
    for sig in signals:
        score = score_signal(sig, store, snap, smt)
        sig.confluence_score = score.total
        sig.confluence_breakdown = dict(score.components)

    # KOD spikes for any signals we just emitted, against later candles.
    kods = []
    for sig in signals:
        after = [c for c in candles if c.open_time > sig.detected_at]
        k = detect_kod(sig, after)
        if k is not None:
            kods.append(k)

    # SMT reading on the asset's dominant direction over the window.
    smt_reading = None
    if pair_candles:
        # Use the last signal's direction; or default to bearish if none.
        direction = signals[-1].direction if signals else Direction.BEARISH
        smt_reading = smt.reading(args.symbol, tf, direction)

    write_chart_html(
        candles, signals, out,
        kods=kods, smt_reading=smt_reading,
        title=f"{args.symbol} {tf.value}  ·  {len(candles)} bars  "
              f"·  {len(signals)} signals  ·  {len(kods)} KOD",
        refresh_seconds=args.refresh,
    )
    abs_path = out.resolve()
    logging.info("chart written: %s  →  file://%s", out, abs_path)
    return 0


async def _run_chart_watch(args: argparse.Namespace) -> int:
    """Re-render the chart every `args.watch` seconds until interrupted.

    The HTML is meta-refresh-tagged at the same cadence so any browser
    pointed at file://.../chart.html will reload automatically.
    """
    args.refresh = max(args.refresh, args.watch)
    try:
        while True:
            await _run_chart_once(args)
            await asyncio.sleep(args.watch)
    except (KeyboardInterrupt, asyncio.CancelledError):
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
        if args.cmd == "chart":
            if args.watch > 0:
                return asyncio.run(_run_chart_watch(args))
            return asyncio.run(_run_chart_once(args))
        return asyncio.run(_run_scan(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
