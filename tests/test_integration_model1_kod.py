"""End-to-end tests for Model #1 + KOD integration through the runtime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.backtest import BacktestRunner
from crt.context import Tier
from crt.detector import detect_model1, model1_to_signal
from crt.models import CRTSubtype, Direction, PositionStatus, Timeframe
from crt.paper import PaperConfig

from tests.conftest import first_ts, make_filler, mk_candle

TF = Timeframe.H1
SYM = "BTC_USDT"


def _bullish_model1_sequence(start):
    """Filler + thick-bearish trigger + close-back-up trigger setting up
    a bullish Model #1."""
    filler = make_filler(SYM, TF, start, 35, base=100.0, body=0.3)
    raised = list(filler)
    # Engineer an old low at ~97.5 at index 5.
    t = raised[5].open_time
    raised[5] = mk_candle(SYM, TF, t, 100.0, 100.5, 97.5, 99.5)
    t_thick = raised[-1].open_time + timedelta(hours=1)
    thick = mk_candle(SYM, TF, t_thick, 99.5, 100.0, 97.0, 97.4)
    trigger = mk_candle(SYM, TF, t_thick + timedelta(hours=1),
                        97.4, 101.0, 97.3, 100.5)
    return raised + [thick, trigger]


def test_model1_to_signal_carries_overrides():
    candles = _bullish_model1_sequence(first_ts())
    m1s = detect_model1(candles)
    assert m1s
    sig = model1_to_signal(m1s[-1])
    assert sig.subtype is CRTSubtype.MODEL_1
    assert sig.direction is Direction.BULLISH
    assert sig.entry_override is not None
    assert sig.stop_override is not None
    # Stop must sit below entry (this is a bullish trade).
    assert sig.stop_override < sig.entry_override


def test_paper_engine_honors_model1_entry_and_stop_overrides():
    from crt.paper import PaperEngine
    candles = _bullish_model1_sequence(first_ts())
    m1 = detect_model1(candles)[-1]
    sig = model1_to_signal(m1)
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pos = engine.on_signal(sig)
    assert pos is not None
    assert pos.entry_price == sig.entry_override
    assert pos.stop_loss == sig.stop_override


def test_backtest_emits_model1_signals_when_present():
    # Anchor sequence at a HIGH-tier hour so the time filter passes.
    start = datetime(2024, 1, 5, 14, tzinfo=timezone.utc)  # 09:00 NY EST
    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(risk_per_trade=100.0),
        min_tier=Tier.LOW,
        require_smc_grounding=False,
    )
    runner.feed(_bullish_model1_sequence(start))
    report = runner.report()
    assert any(s.subtype is CRTSubtype.MODEL_1 for s in report.signals), report.signals


def test_kod_moves_stop_to_break_even_in_backtest():
    """A bullish CRT prints, then 3 candles later a KOD spike-down + recovery
    + confirmation prints. By the time the confirmation candle is processed
    the position should carry a KOD note AND have its stop moved to entry.

    KOD detector needs 3 post-signal candles (baseline, spike, confirm),
    so the test must avoid the position closing at TP2 before all three
    arrive."""
    from datetime import timedelta as td
    filler = make_filler(SYM, TF, datetime(2024, 1, 5, 14, tzinfo=timezone.utc),
                         30, base=100.0, body=0.4)
    t = filler[-1].open_time + td(hours=1)
    # Classic Type-1 bullish CRT.
    c1 = mk_candle(SYM, TF, t, 100.0, 100.5, 98.0, 98.5)
    c2 = mk_candle(SYM, TF, t + td(hours=1), 98.5, 99.2, 97.6, 99.0)
    c3 = mk_candle(SYM, TF, t + td(hours=2), 99.0, 102.0, 98.8, 101.5)
    # c4: retrace candle — straddles the computed entry (~98.25) so the
    # pending limit fills, AND becomes the baseline post-signal candle
    # for KOD rolling-extreme tracking. Stay below TP1 (=99.25) so the
    # TP1 trail isn't what moves the stop.
    c4 = mk_candle(SYM, TF, t + td(hours=3), 99.0, 99.2, 98.10, 99.1)
    # KOD spike-down: low dips below c4.low * (1 - 0.0015), body recovers
    # above c4.low. Must stay above paper stop (~97.35).
    kod_spike = mk_candle(SYM, TF, t + td(hours=4), 98.50, 98.60, 97.94, 98.15)
    # Confirmation: closes above kod_spike.high, but not above TP1 yet.
    kod_confirm = mk_candle(SYM, TF, t + td(hours=5), 98.15, 98.80, 98.10, 98.70)

    runner = BacktestRunner(
        symbols=[SYM], timeframes=[TF],
        paper_config=PaperConfig(risk_per_trade=100.0),
        min_tier=Tier.LOW,
        require_smc_grounding=False,
    )
    runner.feed(filler + [c1, c2, c3, c4, kod_spike, kod_confirm])
    report = runner.report()
    has_kod_note = any(
        any(n.startswith("KOD") for n in p.notes) for p in report.positions
    )
    assert has_kod_note, [p.notes for p in report.positions]
    # Stop should have been moved to break-even (entry_price).
    kod_pos = next(p for p in report.positions if any("KOD" in n for n in p.notes))
    assert kod_pos.stop_loss == kod_pos.entry_price
