"""Model #1 — single-candle trigger detector.

Per CRT Secrets §P2.1 the pattern is:

Bearish Model #1:
  1. Price stabs into an old high (turtle soup).
  2. A THICK up-close candle prints inside/just past the level.
  3. The NEXT candle closes BELOW the thick candle's low → trigger fires.
  Entry on close, stop above the thick candle's high.

Bullish Model #1: mirror — old low stabbed, thick down-close candle, next
candle closes ABOVE its high.

The detector slides over a (symbol, tf) window. For each candle i:
  - Check whether candle i-1 is a "thick" body (>= 1.5× rolling-median body).
  - Check whether the candle i-2 wicked beyond a recent swing extreme
    (= the turtle soup precondition).
  - For bearish: thick-i-1 is bullish AND candle i closes below thick-i-1.low.
  - For bullish: thick-i-1 is bearish AND candle i closes above thick-i-1.high.

Output: `Model1Signal` with the trigger candle, the thick candle, the
swing level that was souped, and the SL/TP geometry.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from crt.models import CRTSubtype, Candle, Direction, Signal, Timeframe


THICK_BODY_MULTIPLIER = 1.5
SWING_LOOKBACK = 30  # how many candles back to scan for an "old high/low"


@dataclass(slots=True)
class Model1Signal:
    symbol: str
    tf: str
    direction: Direction
    detected_at: datetime
    thick_candle: Candle           # the trigger candle
    trigger_candle: Candle         # the one that closed back through
    swept_level: float             # the old high (bearish) or low (bullish)
    stop_loss: float
    entry: float
    target: float                  # first take-profit (50% rule via inverse of move)

    @property
    def note(self) -> str:
        return f"Model #1 {self.direction.value}; thick body @ {self.thick_candle.open_time.isoformat()}"


def _median_body(candles: Sequence[Candle]) -> float:
    bodies = [c.body for c in candles if c.body > 0]
    return statistics.median(bodies) if bodies else 0.0


def _recent_swing_high(candles: Sequence[Candle], up_to: int) -> float | None:
    """Return the highest high in candles[max(0, up_to-SWING_LOOKBACK):up_to]."""
    window = candles[max(0, up_to - SWING_LOOKBACK): up_to]
    if not window:
        return None
    return max(c.high for c in window)


def _recent_swing_low(candles: Sequence[Candle], up_to: int) -> float | None:
    window = candles[max(0, up_to - SWING_LOOKBACK): up_to]
    if not window:
        return None
    return min(c.low for c in window)


def detect_model1(
    candles: Sequence[Candle],
) -> list[Model1Signal]:
    """Scan a chronological window for Model #1 triggers.

    Designed for a recent rolling window; the caller decides how often
    to invoke (typically once per closed candle).
    """
    out: list[Model1Signal] = []
    if len(candles) < SWING_LOOKBACK + 3:
        return out

    for i in range(SWING_LOOKBACK + 2, len(candles)):
        trigger = candles[i]
        thick = candles[i - 1]
        baseline = candles[max(0, i - SWING_LOOKBACK - 1): i - 1]
        median = _median_body(baseline)
        if median <= 0 or thick.body < THICK_BODY_MULTIPLIER * median:
            continue

        # Bearish Model #1: thick is bullish, trigger closes below thick.low
        if thick.is_bullish and trigger.close < thick.low:
            swing_high = _recent_swing_high(candles, i - 1)
            if swing_high is None:
                continue
            # The thick candle's high must have pierced or matched the swing high
            # (the turtle soup of an old high).
            if thick.high < swing_high * 0.999:
                continue
            entry = trigger.close
            stop = thick.high
            # First target = 50% retracement to the recent swing low.
            swing_low = _recent_swing_low(candles, i - 1)
            target = (swing_high + (swing_low or thick.low)) / 2
            out.append(Model1Signal(
                symbol=trigger.symbol, tf=trigger.tf.value,
                direction=Direction.BEARISH,
                detected_at=trigger.open_time,
                thick_candle=thick, trigger_candle=trigger,
                swept_level=swing_high,
                stop_loss=stop, entry=entry, target=target,
            ))
            continue

        # Bullish Model #1: thick is bearish, trigger closes above thick.high
        if (not thick.is_bullish) and trigger.close > thick.high:
            swing_low = _recent_swing_low(candles, i - 1)
            if swing_low is None:
                continue
            if thick.low > swing_low * 1.001:
                continue
            entry = trigger.close
            stop = thick.low
            swing_high = _recent_swing_high(candles, i - 1)
            target = (swing_low + (swing_high or thick.high)) / 2
            out.append(Model1Signal(
                symbol=trigger.symbol, tf=trigger.tf.value,
                direction=Direction.BULLISH,
                detected_at=trigger.open_time,
                thick_candle=thick, trigger_candle=trigger,
                swept_level=swing_low,
                stop_loss=stop, entry=entry, target=target,
            ))
    return out


def model1_to_signal(m1: Model1Signal) -> Signal:
    """Translate a Model1Signal into the runtime's universal Signal so the
    paper engine, TUI, confluence scorer and chart can all consume it.

    Model #1 uses its own entry/stop geometry (entry at trigger close,
    stop just past the thick candle's far edge), so we set the
    entry_override / stop_override fields and leave the CRT-flavored
    range_high/low pointed at the trigger/thick zone for chart overlays.
    """
    if m1.direction is Direction.BULLISH:
        # Bullish trigger: thick is bearish; entry above thick.high.
        range_high = m1.trigger_candle.high
        range_low = m1.thick_candle.low
        lhf = (m1.entry + m1.target) / 2
        initial_dol = m1.target
    else:
        range_high = m1.thick_candle.high
        range_low = m1.trigger_candle.low
        lhf = (m1.entry + m1.target) / 2
        initial_dol = m1.target

    return Signal(
        symbol=m1.symbol, tf=Timeframe(m1.tf),
        subtype=CRTSubtype.MODEL_1, direction=m1.direction,
        detected_at=m1.detected_at,
        range_high=range_high, range_low=range_low,
        purge_price=m1.swept_level,
        confidence=0.7,
        lhf=lhf, initial_dol=initial_dol,
        note=m1.note,
        entry_override=m1.entry,
        stop_override=m1.stop_loss,
    )
