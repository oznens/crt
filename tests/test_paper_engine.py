"""End-to-end paper engine sanity: pending → filled → SL/TP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.models import CRTSubtype, Direction, PositionStatus, Signal, Timeframe
from crt.paper import PaperEngine
from crt.paper.engine import PaperConfig

from tests.conftest import mk_candle

SYM = "BTC_USDT"
TF = Timeframe.H1


def _bullish_signal() -> Signal:
    return Signal(
        symbol=SYM, tf=TF, subtype=CRTSubtype.CLASSIC_3, direction=Direction.BULLISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0,
        purge_price=89.0, confidence=0.8,
        lhf=95.0, initial_dol=100.0, extended_dol=None,
    )


def test_paper_signal_parks_pending_order():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    assert pending is not None
    assert pending.status is PositionStatus.PENDING
    assert pending.entry_price > sig.range_low
    assert pending.stop_loss < sig.purge_price
    assert engine.pending_orders == [pending]
    assert engine.open_positions == []


def test_pending_order_fills_when_price_retraces_into_entry():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    # Entry is just above 90 (range_low). A candle with low ≤ entry ≤ high
    # should fill the limit.
    c = mk_candle(SYM, TF, datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                  o=93.0, h=94.0, low=90.5, c=93.5)
    engine.on_candle(c)
    assert pending.status is PositionStatus.OPEN
    assert pending in engine.open_positions
    assert engine.pending_orders == []
    assert pending.filled_at == c.open_time


def test_pending_cancels_when_stop_hits_before_fill():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    # Big bearish candle wipes through the stop without ever touching entry.
    c = mk_candle(SYM, TF, datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                  o=92.5, h=92.8, low=85.0, c=86.0)
    closed = engine.on_candle(c)
    assert pending.status is PositionStatus.PENDING_CANCELLED
    assert pending in closed
    assert engine.pending_orders == []
    # Cancelled pending is in closed_positions but with zero realized pnl.
    assert pending in engine.closed_positions
    assert pending.realized_pnl == 0.0


def test_pending_expires_after_lifetime_candles():
    from crt.paper.engine import PENDING_LIFETIME_CANDLES
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    t0 = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    # Feed candles that stay above entry (no fill) and above stop (no cancel).
    for i in range(PENDING_LIFETIME_CANDLES + 1):
        c = mk_candle(SYM, TF, t0 + timedelta(hours=i),
                      o=97.0, h=98.0, low=96.5, c=97.5)
        engine.on_candle(c)
    assert pending.status is PositionStatus.PENDING_EXPIRED


def test_filled_position_closes_on_stop():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    t0 = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    # First candle fills.
    fill = mk_candle(SYM, TF, t0, o=93.0, h=94.0, low=90.5, c=93.5)
    engine.on_candle(fill)
    assert pending.status is PositionStatus.OPEN
    # Second candle smashes through the stop.
    sl = mk_candle(SYM, TF, t0 + timedelta(hours=1),
                   o=92.0, h=92.5, low=85.0, c=86.0)
    closed = engine.on_candle(sl)
    assert pending.status is PositionStatus.CLOSED_SL
    assert pending in closed
    assert pending.realized_pnl < 0


def test_filled_position_tp1_then_tp2_with_break_even_trail():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pending = engine.on_signal(sig)
    t0 = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    fill = mk_candle(SYM, TF, t0, o=93.0, h=94.0, low=90.5, c=93.5)
    engine.on_candle(fill)
    entry = pending.entry_price
    # Candle hits TP1 (lhf = 95).
    c1 = mk_candle(SYM, TF, t0 + timedelta(hours=1), o=94.0, h=95.5, low=93.0, c=95.0)
    engine.on_candle(c1)
    assert pending.status is PositionStatus.TP1
    assert pending.stop_loss == entry  # break-even trail
    # Next candle rips to TP2 (initial_dol = 100).
    c2 = mk_candle(SYM, TF, t0 + timedelta(hours=2), o=95.0, h=101.0, low=94.0, c=100.5)
    closed = engine.on_candle(c2)
    assert pending.status is PositionStatus.CLOSED_TP
    assert pending in closed
    assert pending.realized_pnl > 0
