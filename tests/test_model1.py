"""Model #1 single-candle trigger detector."""

from __future__ import annotations

from datetime import timedelta

from crt.detector import detect_model1
from crt.models import Direction, Timeframe

from tests.conftest import first_ts, make_filler, mk_candle

TF = Timeframe.H1
SYM = "BTC_USDT"


def test_bearish_model1_fires_after_old_high_sweep():
    filler = make_filler(SYM, TF, first_ts(), 35, base=100.0, body=0.3)
    # Engineer an "old high" at 102.0 around index 5 by raising one filler candle.
    raised = list(filler)
    t = raised[5].open_time
    raised[5] = mk_candle(SYM, TF, t, 100.0, 102.5, 99.5, 100.5)
    # Continue filler then add the Model #1 pattern.
    t_thick = raised[-1].open_time + timedelta(hours=1)
    # Thick BULLISH candle whose high pierces the old high at 102.5.
    thick = mk_candle(SYM, TF, t_thick, 100.5, 103.0, 100.4, 102.6)  # body 2.1 (huge)
    # Trigger candle closes BELOW thick.low (100.4).
    trigger = mk_candle(SYM, TF, t_thick + timedelta(hours=1),
                        102.0, 102.0, 99.5, 100.0)
    signals = detect_model1(raised + [thick, trigger])
    bears = [s for s in signals if s.direction is Direction.BEARISH]
    assert bears, signals
    sig = bears[-1]
    assert sig.thick_candle is thick
    assert sig.trigger_candle is trigger
    assert sig.stop_loss == thick.high


def test_bullish_model1_fires_after_old_low_sweep():
    filler = make_filler(SYM, TF, first_ts(), 35, base=100.0, body=0.3)
    raised = list(filler)
    t = raised[5].open_time
    raised[5] = mk_candle(SYM, TF, t, 100.0, 100.5, 97.5, 99.5)  # old low 97.5
    t_thick = raised[-1].open_time + timedelta(hours=1)
    # Thick BEARISH candle whose low pierces the old low.
    thick = mk_candle(SYM, TF, t_thick, 99.5, 100.0, 97.0, 97.4)  # body 2.1
    # Trigger candle closes ABOVE thick.high (100.0).
    trigger = mk_candle(SYM, TF, t_thick + timedelta(hours=1),
                        97.4, 101.0, 97.3, 100.5)
    signals = detect_model1(raised + [thick, trigger])
    bulls = [s for s in signals if s.direction is Direction.BULLISH]
    assert bulls, signals
    sig = bulls[-1]
    assert sig.stop_loss == thick.low


def test_no_model1_when_body_not_thick():
    """A normal-sized body should never qualify even with the geometry."""
    filler = make_filler(SYM, TF, first_ts(), 35, base=100.0, body=0.3)
    t_thick = filler[-1].open_time + timedelta(hours=1)
    # Body of only 0.3 (same as filler median).
    thick = mk_candle(SYM, TF, t_thick, 100.0, 102.6, 99.9, 100.3)
    trigger = mk_candle(SYM, TF, t_thick + timedelta(hours=1),
                        100.3, 100.3, 99.0, 99.5)
    assert detect_model1(filler + [thick, trigger]) == []


def test_no_model1_when_old_high_not_swept():
    """Thick body with no old-high stab → no signal."""
    filler = make_filler(SYM, TF, first_ts(), 35, base=100.0, body=0.3)
    t_thick = filler[-1].open_time + timedelta(hours=1)
    # Thick body but high never reaches anything meaningful above filler median highs.
    thick = mk_candle(SYM, TF, t_thick, 100.0, 100.5, 99.9, 100.4)
    trigger = mk_candle(SYM, TF, t_thick + timedelta(hours=1),
                        100.4, 100.5, 99.0, 99.5)
    assert detect_model1(filler + [thick, trigger]) == []
