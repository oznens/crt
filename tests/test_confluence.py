"""Confluence scoring on synthetic signals + canned SMC snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd

from crt.context.confluence import ConfluenceScore, score_signal
from crt.models import CRTSubtype, Direction, Signal, Timeframe
from crt.smc import SMCSnapshot
from crt.store import CandleStore

from tests.conftest import mk_candle


NY = "America/New_York"


def _bullish_signal(purge: float = 95.0) -> Signal:
    return Signal(
        symbol="BTC_USDT", tf=Timeframe.H1, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BULLISH,
        detected_at=datetime(2024, 6, 5, 13, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0, purge_price=purge,
        confidence=0.8, lhf=95.0, initial_dol=100.0,
    )


def _store_with_kill_zone_candle() -> CandleStore:
    """Latest candle for BTC_USDT 1h lands on 09:00 NY (HIGH tier)."""
    store = CandleStore()
    # 09:00 NY = 13:00 UTC in summer (EDT). Use winter to avoid DST confusion.
    # Jan 5, 2024 13:00 UTC → 08:00 EST. So use 14:00 UTC = 09:00 EST.
    t = datetime(2024, 1, 5, 14, tzinfo=timezone.utc)
    store.append(mk_candle("BTC_USDT", Timeframe.H1, t, 99, 100, 99, 100))
    return store


def _empty_snap() -> SMCSnapshot:
    empty = pd.DataFrame()
    return SMCSnapshot(empty, empty, empty, empty, empty, empty)


def _snap_with_aligned_fvg(price: float, kind: int = 1) -> SMCSnapshot:
    """Build a snapshot whose FVG frame says `price` sits inside a same-direction FVG."""
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1.5], "volume": [1]})
    fvg = pd.DataFrame({
        "FVG": [kind], "Top": [price + 1], "Bottom": [price - 1],
        "MitigatedIndex": [float("nan")],
    })
    empty = pd.DataFrame()
    return SMCSnapshot(df=df, swings=empty, fvg=fvg, bos_choch=empty,
                       order_blocks=empty, liquidity=empty)


def test_score_signal_credits_kill_zone():
    store = _store_with_kill_zone_candle()
    sig = _bullish_signal()
    sig.detected_at = datetime(2024, 1, 5, 14, tzinfo=timezone.utc)
    snap = _empty_snap()
    score = score_signal(sig, store, snap)
    assert score.total > 0
    assert any("tier_high" in k for k in score.components)


def test_score_signal_credits_aligned_fvg():
    store = _store_with_kill_zone_candle()
    sig = _bullish_signal(purge=95.0)
    snap = _snap_with_aligned_fvg(95.0, kind=1)
    score = score_signal(sig, store, snap)
    assert "fvg_aligned" in score.components
    assert score.components["fvg_aligned"] == 3.0


def test_score_signal_penalizes_opposing_fvg():
    store = _store_with_kill_zone_candle()
    sig = _bullish_signal(purge=95.0)
    snap = _snap_with_aligned_fvg(95.0, kind=-1)
    score = score_signal(sig, store, snap)
    assert "fvg_opposing" in score.components
    assert score.components["fvg_opposing"] == -2.0


def test_score_signal_respects_htf_bias():
    store = _store_with_kill_zone_candle()
    # H1 → W1 per LTF_TO_HTF, so add a bullish weekly candle.
    store.append(mk_candle("BTC_USDT", Timeframe.W1,
                           datetime(2024, 1, 1, tzinfo=timezone.utc),
                           100, 110, 99, 109))
    sig = _bullish_signal()
    snap = _empty_snap()
    score = score_signal(sig, store, snap)
    assert score.components.get("htf_agree") == 2.0
    # Flip the signal to bearish — should now register disagree.
    sig.direction = Direction.BEARISH
    score = score_signal(sig, store, snap)
    assert score.components.get("htf_disagree") == -2.0


def test_score_summary_renders_components():
    score = ConfluenceScore()
    score.add("tier_high", 3.0)
    score.add("fvg_aligned", 3.0)
    text = score.summary()
    assert "tier_high:+3.0" in text
    assert "fvg_aligned:+3.0" in text
    assert "score=+6.0" in text
