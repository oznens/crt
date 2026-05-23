"""Failure-mode classifier for stopped-out paper positions."""

from __future__ import annotations

from datetime import datetime, timezone

from crt.context.smt import SMTMonitor
from crt.models import (
    CRTSubtype,
    Direction,
    PaperPosition,
    PositionStatus,
    Signal,
    Timeframe,
)
from crt.paper.failure_tag import FailureMode, classify
from crt.store import CandleStore

from tests.conftest import mk_candle


def _stopped_position(direction: Direction = Direction.BULLISH) -> PaperPosition:
    sig = Signal(
        symbol="BTC_USDT", tf=Timeframe.H1, subtype=CRTSubtype.CLASSIC_3,
        direction=direction,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0, purge_price=89.0,
        confidence=0.8, lhf=95.0, initial_dol=100.0,
    )
    return PaperPosition(
        signal=sig,
        entry_price=91.0, stop_loss=88.0, take_profits=[95.0, 100.0],
        size=10.0, opened_at=sig.detected_at,
        status=PositionStatus.CLOSED_SL, realized_pnl=-100.0,
    )


def test_closed_tp_is_not_a_failure():
    p = _stopped_position()
    p.status = PositionStatus.CLOSED_TP
    tag = classify(p, CandleStore(), smt=None)
    assert tag.mode is FailureMode.NOT_A_FAILURE


def test_tp1_then_stop_is_half_done():
    p = _stopped_position()
    p.status = PositionStatus.TP1
    tag = classify(p, CandleStore(), smt=None)
    assert tag.mode is FailureMode.HALF_DONE


def test_counter_trend_when_htf_disagrees():
    store = CandleStore()
    # Bearish HTF (W1) candle.
    store.append(mk_candle("BTC_USDT", Timeframe.W1,
                           datetime(2024, 1, 1, tzinfo=timezone.utc),
                           100, 105, 90, 92))  # close < open
    p = _stopped_position(direction=Direction.BULLISH)
    tag = classify(p, store, smt=None)
    assert tag.mode is FailureMode.COUNTER_TREND


def test_smt_wall_when_pair_diverged_opposite_way():
    store = CandleStore()
    # No HTF candle so HTF check is neutral.
    # Build BTC: just made a fresh low across 4 bars.
    from datetime import timedelta
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, (o, h, low, c) in enumerate([
        (100, 101, 99, 100), (100, 100, 96, 96.5),
        (96.5, 97, 93, 93.5), (93.5, 94, 90, 90.5),
    ]):
        store.append(mk_candle("BTC_USDT", Timeframe.H1,
                               t + timedelta(hours=i), o, h, low, c))
    # ETH did NOT make a new low alongside.
    for i, (o, h, low, c) in enumerate([
        (10, 10.5, 9.8, 10), (10, 10.2, 9.6, 9.8),
        (9.8, 10, 9.5, 9.7), (9.7, 10, 9.65, 9.9),  # holds above prior lows
    ]):
        store.append(mk_candle("ETH_USDT", Timeframe.H1,
                               t + timedelta(hours=i), o, h, low, c))
    smt = SMTMonitor(store, lookback=4)
    # Trade direction = BEARISH; pair diverged BULLISH-SMT (i.e., opposite).
    p = _stopped_position(direction=Direction.BEARISH)
    tag = classify(p, store, smt=smt)
    assert tag.mode is FailureMode.SMT_WALL


def test_early_invalidate_when_neither_signal():
    store = CandleStore()
    p = _stopped_position()
    tag = classify(p, store, smt=None)
    assert tag.mode is FailureMode.EARLY_INVALIDATE
