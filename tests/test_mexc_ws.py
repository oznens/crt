"""Pure-function tests for the MEXC WS parser and close-detector."""

from __future__ import annotations

import json

from crt.data.mexc_ws import (
    _CloseDetector,
    build_subscribe_messages,
    parse_kline_push,
)
from crt.models import Timeframe


def _push(symbol: str, interval: str, t: int, o: float, h: float, low: float, c: float, q: float = 1.0) -> dict:
    return {
        "channel": "push.kline",
        "data": {
            "symbol": symbol, "interval": interval,
            "t": t, "o": o, "h": h, "l": low, "c": c, "q": q,
        },
        "ts": t * 1000,
    }


def test_parse_kline_push_maps_fields():
    parsed = parse_kline_push(_push("BTC_USDT", "Min15", 1_700_000_000, 30000, 30100, 29950, 30050))
    assert parsed is not None
    candle, partial = parsed
    assert candle.symbol == "BTC_USDT"
    assert candle.tf is Timeframe.M15
    assert candle.open == 30000
    assert candle.high == 30100
    assert candle.low == 29950
    assert candle.close == 30050
    assert candle.closed is False
    assert partial is True


def test_parse_ignores_non_kline_channels():
    assert parse_kline_push({"channel": "push.depth", "data": {}}) is None
    assert parse_kline_push({"method": "pong"}) is None


def test_parse_handles_unknown_interval():
    msg = _push("BTC_USDT", "Decade", 1, 1, 1, 1, 1)
    assert parse_kline_push(msg) is None


def test_close_detector_emits_on_timestamp_rollover():
    det = _CloseDetector()
    # First push: just stored, no closure.
    first = _push("BTC_USDT", "Min15", 1_700_000_000, 100, 101, 99, 100.5)
    closed = det.feed(parse_kline_push(first)[0])
    assert closed is None
    # Update to same bar (same t) refines high/low — still no closure.
    update = _push("BTC_USDT", "Min15", 1_700_000_000, 100, 102, 99, 101.5)
    closed = det.feed(parse_kline_push(update)[0])
    assert closed is None
    # Next push for the next bar → previous closes.
    nxt = _push("BTC_USDT", "Min15", 1_700_000_900, 101.5, 101.8, 101.0, 101.6)
    closed = det.feed(parse_kline_push(nxt)[0])
    assert closed is not None
    assert closed.closed is True
    assert closed.high == 102      # carried final snapshot
    assert closed.close == 101.5


def test_close_detector_keeps_independent_state_per_key():
    det = _CloseDetector()
    btc = _push("BTC_USDT", "Min15", 1_700_000_000, 100, 100, 100, 100)
    eth = _push("ETH_USDT", "Min15", 1_700_000_000, 50, 50, 50, 50)
    assert det.feed(parse_kline_push(btc)[0]) is None
    assert det.feed(parse_kline_push(eth)[0]) is None
    # BTC rolls over; ETH untouched.
    btc_next = _push("BTC_USDT", "Min15", 1_700_000_900, 100, 100, 100, 100)
    closed = det.feed(parse_kline_push(btc_next)[0])
    assert closed is not None and closed.symbol == "BTC_USDT"


def test_build_subscribe_messages_one_per_pair():
    pairs = [("BTC_USDT", Timeframe.M15), ("ETH_USDT", Timeframe.H1)]
    msgs = build_subscribe_messages(pairs)
    decoded = [json.loads(m) for m in msgs]
    assert decoded[0]["method"] == "sub.kline"
    assert decoded[0]["param"]["symbol"] == "BTC_USDT"
    assert decoded[0]["param"]["interval"] == "Min15"
    assert decoded[1]["param"]["interval"] == "Min60"  # H1 → Min60
