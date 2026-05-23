"""KOD — Kiss of Death detector.

Per CRT Secrets §P2.2:
  KOD is the FINAL turtle soup before price reaches its main target.
  After a CRT setup has already printed, price stages one more counter-
  direction spike (a small false breakout against the active trade's
  bias) and then resumes toward DOL.

This module is fed an existing `Signal` (a confirmed CRT) and a fresh
candle window; it watches the post-signal price action for a KOD spike.

Bearish CRT (target = CRL below):
    - Within `lookahead` candles after the signal, a candle prints whose
      HIGH exceeds the most-recent post-signal high by a meaningful
      margin, but its body closes BACK below that prior high.
    - Confirmation: the next candle closes below the KOD candle's low.

Mirror for bullish CRT.

The KOD signal is NOT a new trade entry — it's a *confirmation* that
the original CRT trade is about to hit its full target. Useful as:
  - tighten stop to break-even / KOD wick
  - move TP-ladder management
  - mark the chart so the operator sees the final fakeout clearly
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from crt.models import Candle, Direction, Signal


LOOKAHEAD = 12
MIN_SPIKE_PCT = 0.0015  # 0.15% spike above/below recent post-signal extreme


@dataclass(slots=True)
class KODSignal:
    """A Kiss of Death confirmation attached to an active CRT setup."""

    parent_signal: Signal
    direction: Direction          # same as parent_signal.direction
    kod_candle: Candle            # the candle that printed the spike
    confirm_candle: Candle        # the candle that closed back through
    spike_price: float            # extreme of the KOD wick
    detected_at: datetime


def detect_kod(
    parent: Signal,
    post_signal_candles: Sequence[Candle],
) -> KODSignal | None:
    """Look for a KOD spike + confirmation in candles printed AFTER `parent`.

    `post_signal_candles` must be the candles whose open_time is strictly
    after `parent.detected_at`. Returns at most one KOD signal — the
    first one in chronological order — or None if not yet present.
    """
    if len(post_signal_candles) < 2:
        return None
    window = list(post_signal_candles[:LOOKAHEAD])
    if not window:
        return None

    bull = parent.direction is Direction.BULLISH

    # `rolling_extreme` tracks the side that the KOD spike will violate:
    # - bullish parent → KOD spikes DOWN → track the rolling LOW.
    # - bearish parent → KOD spikes UP   → track the rolling HIGH.
    if bull:
        rolling_extreme = window[0].low
    else:
        rolling_extreme = window[0].high

    for i in range(1, len(window) - 1):
        c = window[i]
        nxt = window[i + 1]
        if bull:
            # parent wants price up; KOD = spike DOWN then reject UP.
            spike_below = c.low <= rolling_extreme * (1 - MIN_SPIKE_PCT)
            body_recovers = c.close >= rolling_extreme
            confirmed = nxt.close > c.high
            if spike_below and body_recovers and confirmed:
                return KODSignal(
                    parent_signal=parent, direction=Direction.BULLISH,
                    kod_candle=c, confirm_candle=nxt,
                    spike_price=c.low, detected_at=nxt.open_time,
                )
            rolling_extreme = min(rolling_extreme, c.low)
        else:
            # parent wants price down; KOD = spike UP then reject DOWN.
            spike_above = c.high >= rolling_extreme * (1 + MIN_SPIKE_PCT)
            body_recovers = c.close <= rolling_extreme
            confirmed = nxt.close < c.low
            if spike_above and body_recovers and confirmed:
                return KODSignal(
                    parent_signal=parent, direction=Direction.BEARISH,
                    kod_candle=c, confirm_candle=nxt,
                    spike_price=c.high, detected_at=nxt.open_time,
                )
            rolling_extreme = max(rolling_extreme, c.high)
    return None
