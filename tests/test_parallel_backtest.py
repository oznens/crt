"""Parallel backtest aggregation + report shaping."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from crt.backtest import (
    ParallelBacktestReport,
    format_parallel_report,
    parallel_backtest,
)
from crt.context import Tier
from crt.models import Candle, Timeframe
from crt.paper import PaperConfig

from tests.conftest import make_filler, mk_candle


class _FakeMexcClient:
    """Returns canned candles per (symbol, tf) so the parallel runner
    can be driven without touching the network."""

    def __init__(self, data: dict[tuple[str, Timeframe], list[Candle]]):
        self.data = data
        self.calls: list[tuple[str, Timeframe, int]] = []

    async def fetch_klines(self, symbol, tf, limit):
        self.calls.append((symbol, tf, limit))
        return list(self.data.get((symbol, tf), []))


def _bullish_classic_sequence(symbol: str, tf: Timeframe, start: datetime):
    filler = make_filler(symbol, tf, start, 30, base=100.0, body=0.4)
    t = filler[-1].open_time + timedelta(seconds=tf.seconds)
    c1 = mk_candle(symbol, tf, t, 100.0, 100.5, 98.0, 98.5)
    c2 = mk_candle(symbol, tf, t + timedelta(seconds=tf.seconds), 98.5, 99.2, 97.6, 99.0)
    c3 = mk_candle(symbol, tf, t + timedelta(seconds=tf.seconds * 2),
                   99.0, 102.0, 98.8, 101.5)
    c4 = mk_candle(symbol, tf, t + timedelta(seconds=tf.seconds * 3),
                   101.5, 103.0, 101.0, 102.5)  # hits both TPs
    return filler + [c1, c2, c3, c4]


def _flat_sequence(symbol: str, tf: Timeframe, start: datetime):
    return make_filler(symbol, tf, start, 30, base=100.0, body=0.3)


def test_parallel_backtest_aggregates_per_symbol_reports():
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)  # NY 09:00 EDT
    tf = Timeframe.H1
    data = {
        ("BTC_USDT", tf): _bullish_classic_sequence("BTC_USDT", tf, start),
        ("ETH_USDT", tf): _flat_sequence("ETH_USDT", tf, start),
        ("SOL_USDT", tf): _flat_sequence("SOL_USDT", tf, start),
    }
    client = _FakeMexcClient(data)

    report = asyncio.run(parallel_backtest(
        client, ["BTC_USDT", "SOL_USDT"], [tf],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.LOW,
        bars=60,
        concurrency=2,
    ))

    assert isinstance(report, ParallelBacktestReport)
    assert set(report.per_symbol.keys()) == {"BTC_USDT", "SOL_USDT"}
    # BTC should have signals and a winner; SOL should be flat.
    btc = report.per_symbol["BTC_USDT"]
    sol = report.per_symbol["SOL_USDT"]
    assert btc.wins >= 1
    assert sol.wins == 0 and sol.losses == 0
    # Aggregate properties
    assert report.starting_balance == 10_000.0
    assert report.total_pnl > 0


def test_parallel_backtest_loads_correlated_pair():
    """When SMTMonitor knows a pair, the parallel runner must also fetch it."""
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)
    tf = Timeframe.H1
    data = {
        ("BTC_USDT", tf): _bullish_classic_sequence("BTC_USDT", tf, start),
        ("ETH_USDT", tf): _flat_sequence("ETH_USDT", tf, start),
    }
    client = _FakeMexcClient(data)
    asyncio.run(parallel_backtest(
        client, ["BTC_USDT"], [tf],
        paper_config=PaperConfig(risk_per_trade=100.0),
        min_tier=Tier.LOW, bars=60, concurrency=1,
    ))
    fetched = {(s, t) for s, t, _ in client.calls}
    assert ("BTC_USDT", tf) in fetched
    assert ("ETH_USDT", tf) in fetched  # the pair was pre-loaded


def test_by_symbol_pnl_sorts_descending():
    """Direct construction so we don't need a runner to test the report API."""
    from crt.backtest.engine import BacktestReport
    a = BacktestReport(
        symbols=["A"], timeframes=[Timeframe.H1],
        starting_balance=1000.0, ending_balance=1300.0,
        signals=[], positions=[],
    )
    b = BacktestReport(
        symbols=["B"], timeframes=[Timeframe.H1],
        starting_balance=1000.0, ending_balance=900.0,
        signals=[], positions=[],
    )
    rep = ParallelBacktestReport(per_symbol={"A": a, "B": b},
                                 starting_balance=1000.0)
    ranked = rep.by_symbol_pnl()
    assert ranked == [("A", 300.0), ("B", -100.0)]
    assert rep.total_pnl == 200.0


def test_format_parallel_report_renders_top_and_bottom():
    from crt.backtest.engine import BacktestReport
    per_symbol = {}
    for i in range(12):
        per_symbol[f"S{i}_USDT"] = BacktestReport(
            symbols=[f"S{i}_USDT"], timeframes=[Timeframe.H1],
            starting_balance=1000.0,
            ending_balance=1000.0 + (i - 6) * 50,
            signals=[], positions=[],
        )
    rep = ParallelBacktestReport(per_symbol=per_symbol, starting_balance=1000.0)
    text = format_parallel_report(rep, top=3)
    assert "Top 3 winners" in text
    assert "Bottom 3 losers" in text
    assert "Total PnL" in text
