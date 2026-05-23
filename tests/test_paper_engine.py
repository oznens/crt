"""End-to-end paper engine sanity: open on signal, stop or take profit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.models import CRTSubtype, Direction, Signal, Timeframe
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


def test_paper_opens_position_on_signal():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pos = engine.on_signal(sig)
    assert pos is not None
    # entry slightly above range low, stop slightly below the purge wick
    assert pos.entry_price > sig.range_low
    assert pos.stop_loss < sig.purge_price
    assert pos.take_profits[0] == sig.lhf
    assert pos.take_profits[1] == sig.initial_dol


def test_paper_closes_on_stop():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    engine.on_signal(sig)
    # candle that dips below stop
    c = mk_candle(SYM, TF, datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                  o=92.0, h=92.5, low=85.0, c=86.0)
    closed = engine.on_candle(c)
    assert len(closed) == 1
    assert engine.open_positions == []
    assert engine.closed_positions[0].realized_pnl < 0


def test_paper_takes_profit_at_dol():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    sig = _bullish_signal()
    pos = engine.on_signal(sig)
    # First candle hits TP1 but doesn't touch TP2 yet
    t0 = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    c1 = mk_candle(SYM, TF, t0, o=92.0, h=95.5, low=91.0, c=95.0)
    engine.on_candle(c1)
    assert pos.status.value == "tp1_hit"
    # Next candle pushes through initial DOL → full close at TP2
    c2 = mk_candle(SYM, TF, t0 + timedelta(hours=1), o=95.0, h=101.0, low=94.0, c=100.5)
    closed = engine.on_candle(c2)
    assert len(closed) == 1
    assert engine.closed_positions[0].realized_pnl > 0
