"""Sanity checks for the smc bridge: Candle → DataFrame → indicators."""

from __future__ import annotations

import numpy as np

from crt.models import Timeframe
from crt.smc import (
    candles_to_df,
    compute,
    latest_bearish_fvg,
    latest_bullish_fvg,
    price_in_fvg,
    recent_bos,
)

from tests.conftest import first_ts, make_filler, mk_candle


def _trending_candles(n: int = 60, slope: float = 0.5):
    """Generate a noisy uptrend with enough zigzag to produce real swings."""
    from datetime import timedelta
    rng = np.random.default_rng(7)
    base = 100.0
    candles = []
    t = first_ts()
    price = base
    for i in range(n):
        # Inject pullbacks every ~7 bars so swing pivots actually form.
        if i % 7 == 0 and i > 0:
            price -= slope * 2.5
        else:
            price += slope + rng.normal(0, 0.3)
        o = price + rng.normal(0, 0.2)
        c = price + rng.normal(0, 0.2)
        h = max(o, c) + abs(rng.normal(0, 0.4))
        low = min(o, c) - abs(rng.normal(0, 0.4))
        candles.append(mk_candle("BTC_USDT", Timeframe.H1, t, o, h, low, c))
        t = t + timedelta(hours=1)
    return candles


def test_candles_to_df_shape():
    candles = make_filler("X", Timeframe.M15, first_ts(), 5)
    df = candles_to_df(candles)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 5
    assert df.index.tz is not None


def test_compute_returns_populated_indicators_on_trend():
    candles = _trending_candles(n=80)
    snap = compute(candles, swing_length=5)
    # An 80-bar trend should produce at least a few swings.
    assert snap.swings["HighLow"].notna().sum() >= 2
    # And the FVG / OB frames should at least be the same length as the input.
    assert len(snap.fvg) == len(candles)
    assert len(snap.bos_choch) == len(candles)
    assert len(snap.order_blocks) == len(candles)


def test_recent_bos_returns_direction_or_none():
    candles = _trending_candles(n=80)
    snap = compute(candles, swing_length=5)
    result = recent_bos(snap, lookback=80)
    # Either None (no BOS detected) or +/-1; never garbage.
    assert result in (None, -1, 1)


def test_fvg_helpers_consistent_with_raw_frame():
    candles = _trending_candles(n=80)
    snap = compute(candles)
    bull = latest_bullish_fvg(snap)
    bear = latest_bearish_fvg(snap)
    # Either may be None — but if present, bottom must be <= top.
    for hit in (bull, bear):
        if hit is not None:
            bottom, top = hit
            assert bottom <= top


def test_price_in_fvg_zero_when_no_fvg():
    candles = make_filler("X", Timeframe.M15, first_ts(), 60, body=0.05)
    snap = compute(candles)
    assert price_in_fvg(snap, 100.0) == 0
