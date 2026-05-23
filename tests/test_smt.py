"""SMT divergence monitor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.context.smt import DEFAULT_PAIRS, SMTMonitor, SMTState
from crt.models import Direction, Timeframe
from crt.store import CandleStore

from tests.conftest import mk_candle

TF = Timeframe.H1


def _series(store: CandleStore, symbol: str, prices: list[tuple[float, float, float, float]]):
    """Feed [(o, h, l, c), ...] candles spaced 1h apart."""
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for (o, h, low, c) in prices:
        store.append(mk_candle(symbol, TF, t, o, h, low, c))
        t = t + timedelta(hours=1)


def test_bearish_smt_when_lead_makes_new_high_pair_lags():
    store = CandleStore()
    # BTC: monotonically rising highs ending in a fresh ATH.
    _series(store, "BTC_USDT", [
        (100, 101, 99, 100),
        (101, 102, 100, 101),
        (102, 103, 101, 102),
        (103, 105, 102, 104),  # new high above all prior
    ])
    # ETH: rising but last bar's high does NOT exceed prior bars'.
    _series(store, "ETH_USDT", [
        (10, 10.5, 9.8, 10.3),
        (10.3, 10.9, 10.2, 10.7),
        (10.7, 11.2, 10.6, 11.0),
        (11.0, 11.1, 10.5, 10.6),  # FAILED to make new high
    ])
    smt = SMTMonitor(store, lookback=4)
    r = smt.reading("BTC_USDT", TF, Direction.BEARISH)
    assert r.state is SMTState.BEARISH
    assert r.is_divergent


def test_bullish_smt_when_lead_makes_new_low_pair_holds():
    store = CandleStore()
    _series(store, "BTC_USDT", [
        (100, 101, 99, 100),
        (100, 100.5, 98, 98.5),
        (98.5, 99, 97, 97.5),
        (97.5, 98, 95, 96),  # new low
    ])
    _series(store, "ETH_USDT", [
        (10, 10.5, 9.8, 10),
        (10, 10.2, 9.6, 9.8),
        (9.8, 9.9, 9.5, 9.6),
        (9.6, 9.8, 9.55, 9.7),  # did not break prior lows
    ])
    smt = SMTMonitor(store, lookback=4)
    r = smt.reading("BTC_USDT", TF, Direction.BULLISH)
    assert r.state is SMTState.BULLISH


def test_no_smt_when_pair_also_makes_extreme():
    store = CandleStore()
    _series(store, "BTC_USDT", [
        (100, 101, 99, 100), (101, 102, 100, 101),
        (102, 103, 101, 102), (103, 105, 102, 104),
    ])
    _series(store, "ETH_USDT", [
        (10, 10.5, 9.8, 10.3), (10.3, 10.9, 10.2, 10.7),
        (10.7, 11.2, 10.6, 11.0), (11.0, 11.5, 10.9, 11.4),  # also new high
    ])
    smt = SMTMonitor(store, lookback=4)
    r = smt.reading("BTC_USDT", TF, Direction.BEARISH)
    assert r.state is SMTState.ALIGNED
    assert not r.is_divergent


def test_no_data_when_pair_missing():
    store = CandleStore()
    _series(store, "BTC_USDT", [(100, 101, 99, 100)])
    smt = SMTMonitor(store, pairs={"BTC_USDT": "ETH_USDT"})
    r = smt.reading("BTC_USDT", TF, Direction.BEARISH)
    assert r.state is SMTState.NO_DATA


def test_default_pair_map_includes_btc_eth():
    assert DEFAULT_PAIRS["BTC_USDT"] == "ETH_USDT"
    assert DEFAULT_PAIRS["ETH_USDT"] == "BTC_USDT"
