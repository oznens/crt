"""Replay-based end-to-end test of the backtest engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.backtest import BacktestRunner
from crt.context import Tier
from crt.models import CRTSubtype, Direction, Timeframe
from crt.paper import PaperConfig

from tests.conftest import make_filler, mk_candle

SYM = "BTC_USDT"
TF = Timeframe.H1


def _bullish_classic_sequence(start: datetime) -> list:
    """Filler + Classic-3 bullish CRT + retrace fill + TP candle.
    c4 straddles entry (~98.25) WITHOUT reaching TP1 (=99.25), so the
    pending order fills clean before c5 takes price to the target."""
    filler = make_filler(SYM, TF, start, 30, base=100.0, body=0.4)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYM, TF, t, 100.0, 100.5, 98.0, 98.5)
    c2 = mk_candle(SYM, TF, t + timedelta(hours=1), 98.5, 99.2, 97.6, 99.0)
    c3 = mk_candle(SYM, TF, t + timedelta(hours=2), 99.0, 102.0, 98.8, 101.5)
    c4 = mk_candle(SYM, TF, t + timedelta(hours=3), 98.50, 99.00, 98.10, 98.70)
    c5 = mk_candle(SYM, TF, t + timedelta(hours=4), 98.70, 103.0, 98.50, 102.5)
    return filler + [c1, c2, c3, c4, c5]


def _classic_then_stop_sequence(start: datetime) -> list:
    filler = make_filler(SYM, TF, start, 30, base=100.0, body=0.4)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYM, TF, t, 100.0, 100.5, 98.0, 98.5)
    c2 = mk_candle(SYM, TF, t + timedelta(hours=1), 98.5, 99.2, 97.6, 99.0)
    c3 = mk_candle(SYM, TF, t + timedelta(hours=2), 99.0, 102.0, 98.8, 101.5)
    c4 = mk_candle(SYM, TF, t + timedelta(hours=3), 98.50, 99.00, 98.10, 98.70)
    c5 = mk_candle(SYM, TF, t + timedelta(hours=4), 98.70, 99.00, 95.00, 95.50)
    return filler + [c1, c2, c3, c4, c5]


def test_backtest_report_records_a_winner():
    # Bullet through midweek NY morning so the kill-zone tier passes.
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)  # 09:00 NY local
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.LOW,
    )
    runner.feed(_bullish_classic_sequence(start))
    report = runner.report()
    assert len(report.signals) >= 1
    assert any(
        s.subtype is CRTSubtype.CLASSIC_3 and s.direction is Direction.BULLISH
        for s in report.signals
    )
    assert report.wins >= 1
    assert report.total_pnl > 0
    assert report.win_rate == 100.0


def test_backtest_report_records_a_loser_and_max_drawdown():
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.LOW,
    )
    runner.feed(_classic_then_stop_sequence(start))
    report = runner.report()
    assert report.losses == 1
    assert report.total_pnl < 0
    # Drawdown should be at least the realized loss
    assert report.max_drawdown <= report.total_pnl


def test_backtest_breakdown_buckets_by_subtype():
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.LOW,
    )
    runner.feed(_bullish_classic_sequence(start))
    breakdown = runner.report().by_subtype()
    assert CRTSubtype.CLASSIC_3 in breakdown
    assert breakdown[CRTSubtype.CLASSIC_3]["trades"] == 1
    assert breakdown[CRTSubtype.CLASSIC_3]["wins"] == 1


def test_backtest_skips_signals_below_time_tier():
    """When the trigger candle lands outside the NY kill zones and the
    min_tier is HIGH, the detector run is suppressed and no positions open.

    Start 14:00 UTC = 10:00 NY local. 30 hourly fillers end at 20:00 UTC the
    next day; c1..c4 then land at 20:00, 21:00, 22:00, 23:00 UTC = 16:00,
    17:00, 18:00, 19:00 NY — only c1 is MEDIUM, c2..c4 are all LOW. With
    min_tier=HIGH, the detector never runs on the trigger candle (c4).
    """
    start = datetime(2024, 6, 5, 14, tzinfo=timezone.utc)
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.HIGH,
    )
    runner.feed(_bullish_classic_sequence(start))
    report = runner.report()
    assert len(report.positions) == 0


def test_format_report_returns_multiline_summary():
    from crt.backtest.engine import format_report
    start = datetime(2024, 6, 5, 13, tzinfo=timezone.utc)
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(starting_balance=10_000.0, risk_per_trade=100.0),
        min_tier=Tier.LOW,
    )
    runner.feed(_bullish_classic_sequence(start))
    text = format_report(runner.report())
    assert "Win rate" in text
    assert "Expectancy" in text
    assert "By subtype" in text
