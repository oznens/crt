"""Each CRT subtype gets a hand-crafted synthetic sequence so we can lock
the detector's geometric rules in place."""

from __future__ import annotations

from datetime import timedelta

from crt.detector import CRTDetector
from crt.models import CRTSubtype, Direction, Timeframe
from crt.store import CandleStore

from tests.conftest import first_ts, make_filler, mk_candle

SYMBOL = "BTC_USDT"
TF = Timeframe.H1


def _seed_store(candles):
    store = CandleStore()
    for c in candles:
        store.append(c)
    return store


def _next_ts(prev, n: int = 1):
    return prev + timedelta(seconds=TF.seconds * n)


def test_type1_classic_bullish_emits_signal():
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0, body=0.4)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    # C1: beefy bearish range candle.
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=100.5, low=98.0, c=98.5)
    # C2: small wick BELOW C1 low, body closes inside C1 range.
    c2 = mk_candle(
        SYMBOL, TF, _next_ts(t),
        o=98.5, h=99.2, low=97.6, c=99.0,
    )
    # C3: bullish expansion closing well above CRH.
    c3 = mk_candle(
        SYMBOL, TF, _next_ts(t, 2),
        o=99.0, h=102.0, low=98.8, c=101.5,
    )
    store = _seed_store(filler + [c1, c2, c3])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert any(
        s.subtype is CRTSubtype.CLASSIC_3 and s.direction is Direction.BULLISH
        for s in sigs
    ), sigs


def test_type1_classic_bearish_emits_signal():
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=102.0, low=99.5, c=101.5)
    c2 = mk_candle(
        SYMBOL, TF, _next_ts(t),
        o=101.5, h=102.4, low=100.6, c=101.0,
    )
    c3 = mk_candle(
        SYMBOL, TF, _next_ts(t, 2),
        o=101.0, h=101.2, low=98.5, c=99.0,
    )
    store = _seed_store(filler + [c1, c2, c3])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert any(
        s.subtype is CRTSubtype.CLASSIC_3 and s.direction is Direction.BEARISH
        for s in sigs
    ), sigs


def test_type2_aggressive_bullish_single_candle():
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=100.5, low=98.0, c=98.5)
    # C2: wick below CRL AND closes above CRH within the same bar.
    c2 = mk_candle(
        SYMBOL, TF, _next_ts(t),
        o=98.5, h=102.0, low=97.5, c=101.5,
    )
    store = _seed_store(filler + [c1, c2])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert any(
        s.subtype is CRTSubtype.AGGRESSIVE_2 and s.direction is Direction.BULLISH
        for s in sigs
    ), sigs


def test_type3_multi_candle_walks_to_target():
    """Type 3 differs from Type 4 (Inside Bar) by NOT keeping every post-C2
    candle inside C1's range — the expansion has started but takes several
    candles to close past CRH."""
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=100.5, low=98.0, c=98.5)
    # C2 purges below CRL, body inside range.
    c2 = mk_candle(SYMBOL, TF, _next_ts(t), o=98.5, h=99.0, low=97.6, c=98.8)
    # C3 wick breaks CRH but close stays below — disqualifies inside-bar pattern.
    c3 = mk_candle(SYMBOL, TF, _next_ts(t, 2), o=98.8, h=100.7, low=98.5, c=99.5)
    # C4 holds gains but still below CRH on close.
    c4 = mk_candle(SYMBOL, TF, _next_ts(t, 3), o=99.5, h=100.3, low=99.2, c=100.0)
    # C5 finally closes through CRH.
    c5 = mk_candle(SYMBOL, TF, _next_ts(t, 4), o=100.0, h=101.5, low=99.8, c=101.0)
    store = _seed_store(filler + [c1, c2, c3, c4, c5])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert any(
        s.subtype is CRTSubtype.MULTI_CANDLE and s.direction is Direction.BULLISH
        for s in sigs
    ), sigs


def test_type4_inside_bar_bullish():
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    # C1: large displacement bar setting the range.
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=102.5, low=97.5, c=98.0)
    crh, crl = c1.high, c1.low
    # C2..C4: inside bars; C3 dips wick just below CRL but body stays inside.
    c2 = mk_candle(SYMBOL, TF, _next_ts(t), o=98.0, h=99.5, low=98.0, c=99.0)
    c3 = mk_candle(SYMBOL, TF, _next_ts(t, 2), o=99.0, h=100.5, low=97.4, c=98.5)
    c4 = mk_candle(SYMBOL, TF, _next_ts(t, 3), o=98.5, h=100.0, low=98.0, c=99.5)
    # C5: explosive breakout above CRH.
    c5 = mk_candle(SYMBOL, TF, _next_ts(t, 4), o=99.5, h=104.0, low=99.4, c=103.5)
    store = _seed_store(filler + [c1, c2, c3, c4, c5])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert any(
        s.subtype is CRTSubtype.INSIDE_BAR and s.direction is Direction.BULLISH
        for s in sigs
    ), sigs
    # confirm geometry
    one = next(s for s in sigs if s.subtype is CRTSubtype.INSIDE_BAR)
    assert one.range_high == crh and one.range_low == crl


def test_no_signal_when_purge_wick_too_shallow():
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=100.5, low=98.0, c=98.5)
    # C2 wick does NOT pierce CRL.
    c2 = mk_candle(SYMBOL, TF, _next_ts(t), o=98.5, h=99.2, low=98.1, c=99.0)
    # Even if c3 expands, the purge precondition fails.
    c3 = mk_candle(SYMBOL, TF, _next_ts(t, 2), o=99.0, h=102.0, low=98.8, c=101.5)
    store = _seed_store(filler + [c1, c2, c3])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    assert not [s for s in sigs if s.direction is Direction.BULLISH], sigs


def test_signal_geometry_lhf_and_initial_dol():
    """LHF must be 50% of range candle, Initial DOL = opposite extreme."""
    filler = make_filler(SYMBOL, TF, first_ts(), 30, base=100.0)
    t = filler[-1].open_time + timedelta(seconds=TF.seconds)
    c1 = mk_candle(SYMBOL, TF, t, o=100.0, h=100.5, low=98.0, c=98.5)
    c2 = mk_candle(SYMBOL, TF, _next_ts(t), o=98.5, h=99.2, low=97.6, c=99.0)
    c3 = mk_candle(SYMBOL, TF, _next_ts(t, 2), o=99.0, h=102.0, low=98.8, c=101.5)
    store = _seed_store(filler + [c1, c2, c3])
    sigs = CRTDetector(store).evaluate(SYMBOL, TF)
    bull = next(
        s for s in sigs
        if s.subtype is CRTSubtype.CLASSIC_3 and s.direction is Direction.BULLISH
    )
    assert bull.lhf == (c1.high + c1.low) / 2
    assert bull.initial_dol == c1.high
    assert bull.range_high == c1.high
    assert bull.range_low == c1.low
