"""Kiss of Death detector — fires AFTER a parent CRT signal prints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.detector import detect_kod
from crt.models import CRTSubtype, Direction, Signal, Timeframe

from tests.conftest import mk_candle

TF = Timeframe.H1
SYM = "BTC_USDT"


def _bearish_parent() -> Signal:
    return Signal(
        symbol=SYM, tf=TF, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BEARISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=110, range_low=100, purge_price=111,
        confidence=0.8, lhf=105, initial_dol=100,
    )


def _bullish_parent() -> Signal:
    return Signal(
        symbol=SYM, tf=TF, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BULLISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100, range_low=90, purge_price=89,
        confidence=0.8, lhf=95, initial_dol=100,
    )


def test_bearish_kod_fires_on_spike_up_then_rejection():
    """Bearish parent CRT is in progress (price drifting down). A KOD spikes
    HIGH (false breakout up) but body closes back into prior range; next
    candle dumps below the KOD low → confirmation."""
    t = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    # Post-signal candles: gentle drop, then a spike-up KOD, then resume drop.
    candles = [
        mk_candle(SYM, TF, t, 108, 109, 107, 107.5),
        mk_candle(SYM, TF, t + timedelta(hours=1), 107.5, 108, 106, 106.5),
        mk_candle(SYM, TF, t + timedelta(hours=2), 106.5, 107, 105, 105.5),
        # KOD candle: high spikes far above prior post-signal extreme (109)
        # but body closes back below 109.
        mk_candle(SYM, TF, t + timedelta(hours=3), 105.5, 112, 105, 108),
        # Confirmation candle: closes BELOW KOD low (105).
        mk_candle(SYM, TF, t + timedelta(hours=4), 108, 108.5, 100, 101),
        mk_candle(SYM, TF, t + timedelta(hours=5), 101, 101.5, 98, 99),
    ]
    sig = detect_kod(_bearish_parent(), candles)
    assert sig is not None, "expected KOD signal"
    assert sig.direction is Direction.BEARISH
    assert sig.kod_candle is candles[3]
    assert sig.confirm_candle is candles[4]


def test_bullish_kod_fires_on_spike_down_then_rejection():
    t = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    candles = [
        mk_candle(SYM, TF, t, 92, 93, 91, 92.5),
        mk_candle(SYM, TF, t + timedelta(hours=1), 92.5, 94, 92, 93.5),
        mk_candle(SYM, TF, t + timedelta(hours=2), 93.5, 95, 93, 94.5),
        # KOD candle: spikes DOWN below prior post-signal extreme low (91)
        # but body closes back above 91.
        mk_candle(SYM, TF, t + timedelta(hours=3), 94.5, 95, 88, 92),
        # Confirmation: next candle closes ABOVE KOD high (95).
        mk_candle(SYM, TF, t + timedelta(hours=4), 92, 96, 91.8, 95.5),
        mk_candle(SYM, TF, t + timedelta(hours=5), 95.5, 98, 95, 97.5),
    ]
    sig = detect_kod(_bullish_parent(), candles)
    assert sig is not None
    assert sig.direction is Direction.BULLISH
    assert sig.kod_candle is candles[3]


def test_no_kod_when_no_meaningful_spike():
    t = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    # Steady drift without any spike beyond the rolling extreme.
    candles = [
        mk_candle(SYM, TF, t + timedelta(hours=i), 108 - i, 108.5 - i, 107 - i, 107.5 - i)
        for i in range(6)
    ]
    assert detect_kod(_bearish_parent(), candles) is None


def test_no_kod_when_window_too_short():
    assert detect_kod(_bearish_parent(), []) is None
    one = [mk_candle(SYM, TF, datetime(2024, 1, 1, tzinfo=timezone.utc),
                     100, 101, 99, 100)]
    assert detect_kod(_bearish_parent(), one) is None
