"""CISD — Change in State of Delivery (ICT concept).

A CISD is the precise confirmation step that comes AFTER a turtle soup:
the next candle's body must close back through the level that was just
swept. Wick-only re-entries don't count.

  Bearish CISD: price wicked above an old high, then a candle's CLOSE
                prints below that swept high → buyers' delivery has
                shifted to sellers' delivery.

  Bullish CISD: price wicked below an old low, then a candle's CLOSE
                prints above that swept low.

When a Signal already exists for the same direction, we compute the
CISD status off the signal's `purge_price` (= the swept level) and the
post-signal candles. The states:

  PENDING       sweep observed, not yet closed back
  ACTIVE        body closed back through → confirmed
  INVALIDATED   price went further past the sweep without closing back
                within `lookahead` candles
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from crt.models import Candle, Direction, Signal


CISD_LOOKAHEAD = 6


class CISDStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    ACTIVE = "active"
    INVALIDATED = "invalidated"


@dataclass(slots=True)
class CISDReading:
    status: CISDStatus
    swept_level: float
    confirm_candle: Candle | None = None


def evaluate_cisd(signal: Signal, post_signal: Sequence[Candle]) -> CISDReading:
    """Classify the CISD state for a confirmed CRT signal."""
    level = signal.purge_price
    if not post_signal:
        return CISDReading(CISDStatus.PENDING, level)

    bull = signal.direction is Direction.BULLISH

    for i, c in enumerate(post_signal[:CISD_LOOKAHEAD]):
        if bull:
            # Bullish CISD: candle close is ABOVE the swept low.
            if c.close > level:
                return CISDReading(CISDStatus.ACTIVE, level, c)
            # Invalidation: price kept driving DOWN past the sweep.
            if c.low < level * 0.985:
                return CISDReading(CISDStatus.INVALIDATED, level)
        else:
            # Bearish CISD: candle close is BELOW the swept high.
            if c.close < level:
                return CISDReading(CISDStatus.ACTIVE, level, c)
            if c.high > level * 1.015:
                return CISDReading(CISDStatus.INVALIDATED, level)

    return CISDReading(CISDStatus.PENDING, level)
