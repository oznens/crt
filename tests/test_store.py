from __future__ import annotations

from datetime import timedelta

from crt.models import Timeframe
from crt.store import CandleStore

from tests.conftest import first_ts, mk_candle

TF = Timeframe.M15


def test_store_appends_and_deduplicates():
    store = CandleStore(maxlen=10)
    t = first_ts()
    c1 = mk_candle("X", TF, t, 1, 2, 1, 1.5)
    c1_replay = mk_candle("X", TF, t, 1, 2.5, 1, 2.0)  # same time, different bar (update)
    c2 = mk_candle("X", TF, t + timedelta(minutes=15), 2, 3, 1.5, 2.5)
    store.append(c1)
    store.append(c1_replay)
    store.append(c2)
    candles = store.get("X", TF)
    assert len(candles) == 2
    # last candle for t is the replayed one
    assert candles[0].high == 2.5
    assert candles[1].close == 2.5


def test_store_respects_max_length():
    store = CandleStore(maxlen=3)
    t = first_ts()
    for i in range(5):
        store.append(mk_candle("X", TF, t + timedelta(minutes=15 * i), 1, 2, 1, 1.5))
    assert len(store.get("X", TF)) == 3
