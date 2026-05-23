"""Time-of-day filters derived from CRT doctrine.

The deck assigns probability windows to candles based on their position
within the parent HTF candle:

- Daily: 2 high-prob sessions per day anchored on 01:00 and 09:00 (NY).
  Per the H4 grid that's the 1AM and 9AM 4-hour bars; on M15/M5 it means
  the kill-zones starting at those hours.
- Weekly: Low/High of the week tends to form Mon–Wed; the opposite extreme
  caps Thu–Fri.
- Monthly: low/high in W1/W2, opposite extreme in W3/W4.

This module exposes pure helpers that classify a candle by its open_time
and returns a probability tier (HIGH / MEDIUM / LOW / SKIP). The detector
runtime can choose to filter by these tiers.

All comparisons use the New-York timezone (`America/New_York`) since the
CRT/ICT framework is anchored to NY session.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from crt.models import Candle, Timeframe

NY = ZoneInfo("America/New_York")


class Tier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SKIP = "skip"


# Daily killzones (NY local time, inclusive start, exclusive end).
# These are the two windows the deck emphasizes per day for LTF entries.
_KILLZONES_NY: list[tuple[int, int]] = [
    (1, 5),    # 01:00 – 05:00 NY  (Asia → London handoff)
    (9, 12),   # 09:00 – 12:00 NY  (NY open session)
]


def _in_window(hour: int, windows: list[tuple[int, int]]) -> bool:
    return any(lo <= hour < hi for lo, hi in windows)


def daily_tier(candle: Candle) -> Tier:
    """Score an intraday candle by NY kill-zone overlap."""
    ny = candle.open_time.astimezone(NY)
    hour = ny.hour
    if _in_window(hour, _KILLZONES_NY):
        return Tier.HIGH
    # The 13:00–16:00 PM session can still produce setups but lower prob.
    if 13 <= hour < 16:
        return Tier.MEDIUM
    return Tier.LOW


def weekly_tier(candle: Candle) -> Tier:
    """Position within the week determines tier on Weekly setups.

    Per doctrine: low/high forms Mon–Wed, opposite extreme Thu–Fri. Saturday
    and Sunday's open hours bridge those weeks — treat as LOW because the
    range candle should not be marked over the weekend.
    """
    ny = candle.open_time.astimezone(NY)
    weekday = ny.weekday()  # Mon=0, Sun=6
    if weekday <= 2:        # Mon–Wed
        return Tier.HIGH
    if weekday <= 4:        # Thu–Fri
        return Tier.HIGH
    return Tier.LOW         # Sat–Sun


def monthly_tier(candle: Candle) -> Tier:
    """Position within the month: W1/W2 vs W3/W4 are both HIGH for different roles."""
    ny = candle.open_time.astimezone(NY)
    # Approximate week of month (1-indexed).
    week = (ny.day - 1) // 7 + 1
    return Tier.HIGH if 1 <= week <= 4 else Tier.MEDIUM


def candle_tier(candle: Candle) -> Tier:
    """Pick the right tier function for the candle's TF."""
    if candle.tf in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30,
                     Timeframe.H1, Timeframe.H4):
        return daily_tier(candle)
    if candle.tf is Timeframe.D1:
        return weekly_tier(candle)
    if candle.tf is Timeframe.W1:
        return monthly_tier(candle)
    return Tier.MEDIUM


def passes_time_filter(candle: Candle, min_tier: Tier = Tier.MEDIUM) -> bool:
    """Should we even bother evaluating CRT setups on this candle?

    Default policy: require MEDIUM or HIGH. Set to Tier.HIGH for stricter,
    or Tier.LOW to disable filtering entirely.
    """
    order = {Tier.SKIP: 0, Tier.LOW: 1, Tier.MEDIUM: 2, Tier.HIGH: 3}
    return order[candle_tier(candle)] >= order[min_tier]


def utc_to_ny(dt: datetime) -> datetime:
    return dt.astimezone(NY)
