"""Time-window and HTF alignment helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from crt.context import (
    Tier,
    candle_tier,
    daily_tier,
    htf_bias,
    monthly_tier,
    parent_tf,
    passes_time_filter,
    signal_aligned_with_htf,
    weekly_tier,
)
from crt.models import Direction, Timeframe
from crt.store import CandleStore

from tests.conftest import mk_candle

NY = ZoneInfo("America/New_York")


def _at_ny(year: int, month: int, day: int, hour: int, tf: Timeframe = Timeframe.M15):
    dt_ny = datetime(year, month, day, hour, tzinfo=NY)
    return mk_candle("BTC_USDT", tf, dt_ny.astimezone(timezone.utc), 1, 1, 1, 1)


def test_daily_tier_high_in_kill_zones():
    # 1AM NY → HIGH
    assert daily_tier(_at_ny(2024, 6, 5, 1)) is Tier.HIGH
    assert daily_tier(_at_ny(2024, 6, 5, 3)) is Tier.HIGH
    # 9AM NY → HIGH (NY open)
    assert daily_tier(_at_ny(2024, 6, 5, 9)) is Tier.HIGH
    assert daily_tier(_at_ny(2024, 6, 5, 11)) is Tier.HIGH


def test_daily_tier_medium_in_pm():
    assert daily_tier(_at_ny(2024, 6, 5, 14)) is Tier.MEDIUM
    assert daily_tier(_at_ny(2024, 6, 5, 15)) is Tier.MEDIUM


def test_daily_tier_low_overnight():
    assert daily_tier(_at_ny(2024, 6, 5, 22)) is Tier.LOW
    assert daily_tier(_at_ny(2024, 6, 5, 0)) is Tier.LOW  # midnight just before 01:00


def test_weekly_tier():
    # Wednesday → HIGH (Mon-Wed bucket)
    assert weekly_tier(_at_ny(2024, 6, 5, 10, Timeframe.D1)) is Tier.HIGH
    # Friday → HIGH (Thu-Fri bucket)
    assert weekly_tier(_at_ny(2024, 6, 7, 10, Timeframe.D1)) is Tier.HIGH
    # Sunday → LOW
    assert weekly_tier(_at_ny(2024, 6, 9, 10, Timeframe.D1)) is Tier.LOW


def test_monthly_tier_buckets_first_four_weeks():
    assert monthly_tier(_at_ny(2024, 6, 3, 10, Timeframe.W1)) is Tier.HIGH      # W1
    assert monthly_tier(_at_ny(2024, 6, 10, 10, Timeframe.W1)) is Tier.HIGH     # W2
    assert monthly_tier(_at_ny(2024, 6, 18, 10, Timeframe.W1)) is Tier.HIGH     # W3
    assert monthly_tier(_at_ny(2024, 6, 25, 10, Timeframe.W1)) is Tier.HIGH     # W4
    assert monthly_tier(_at_ny(2024, 6, 30, 10, Timeframe.W1)) is Tier.MEDIUM   # spillover


def test_candle_tier_routes_by_tf():
    intraday = _at_ny(2024, 6, 5, 10, Timeframe.H1)
    weekly = _at_ny(2024, 6, 5, 10, Timeframe.D1)
    assert candle_tier(intraday) is Tier.HIGH
    assert candle_tier(weekly) is Tier.HIGH


def test_passes_time_filter_threshold_semantics():
    c_high = _at_ny(2024, 6, 5, 10)   # HIGH
    c_low = _at_ny(2024, 6, 5, 22)    # LOW
    assert passes_time_filter(c_high, Tier.HIGH)
    assert not passes_time_filter(c_low, Tier.HIGH)
    assert passes_time_filter(c_low, Tier.LOW)
    assert not passes_time_filter(c_low, Tier.MEDIUM)


def test_parent_tf_map():
    assert parent_tf(Timeframe.M15) is Timeframe.D1
    assert parent_tf(Timeframe.H1) is Timeframe.W1
    assert parent_tf(Timeframe.W1) is None


def test_htf_bias_uses_current_htf_candle_body():
    store = CandleStore()
    t = datetime(2024, 6, 5, tzinfo=timezone.utc)
    # Bullish HTF candle (close > open)
    store.append(mk_candle("BTC_USDT", Timeframe.D1, t, 100, 105, 99, 104))
    assert htf_bias(store, "BTC_USDT", Timeframe.M15) is Direction.BULLISH
    # Update to bearish — htf_bias should follow
    store.append(mk_candle("BTC_USDT", Timeframe.D1, t, 100, 105, 99, 96))
    assert htf_bias(store, "BTC_USDT", Timeframe.M15) is Direction.BEARISH


def test_signal_aligned_with_htf_respects_require_flag():
    store = CandleStore()  # empty, no HTF data
    # Lax mode: no data → pass
    assert signal_aligned_with_htf(store, "BTC_USDT", Timeframe.M15, Direction.BULLISH)
    # Strict mode: no data → block
    assert not signal_aligned_with_htf(
        store, "BTC_USDT", Timeframe.M15, Direction.BULLISH, require=True,
    )

    t = datetime(2024, 6, 5, tzinfo=timezone.utc)
    store.append(mk_candle("BTC_USDT", Timeframe.D1, t, 100, 105, 99, 104))  # bullish HTF
    assert signal_aligned_with_htf(store, "BTC_USDT", Timeframe.M15, Direction.BULLISH)
    assert not signal_aligned_with_htf(store, "BTC_USDT", Timeframe.M15, Direction.BEARISH)
