"""Pure-function tests for the Bybit WS parser + subscribe builder."""

from __future__ import annotations

import json

from crt.data.bybit_ws import build_subscribe_messages, parse_kline_push
from crt.models import Timeframe


def _push(symbol: str, interval: str, start: int, *,
          o: float, h: float, low: float, c: float, vol: float = 1.0,
          confirm: bool = True) -> dict:
    return {
        "topic": f"kline.{interval}.{symbol}",
        "data": [
            {
                "start": start, "end": start + 60_000,
                "interval": interval,
                "open": str(o), "high": str(h), "low": str(low), "close": str(c),
                "volume": str(vol), "turnover": "1",
                "confirm": confirm, "timestamp": start + 1,
            }
        ],
        "ts": start + 1,
    }


def test_parse_kline_push_returns_closed_candle():
    candles = parse_kline_push(_push("BTCUSDT", "15", 1_700_000_000_000,
                                     o=100, h=101, low=99.5, c=100.5))
    assert len(candles) == 1
    c = candles[0]
    assert c.symbol == "BTC_USDT"
    assert c.tf is Timeframe.M15
    assert c.open == 100
    assert c.high == 101
    assert c.close == 100.5
    assert c.closed is True


def test_parse_kline_push_drops_unconfirmed():
    candles = parse_kline_push(_push("BTCUSDT", "15", 1_700_000_000_000,
                                     o=100, h=101, low=99, c=100, confirm=False))
    assert candles == []


def test_parse_ignores_non_kline_topics():
    assert parse_kline_push({"topic": "tickers.BTCUSDT", "data": []}) == []
    assert parse_kline_push({"op": "subscribe"}) == []


def test_parse_handles_unknown_interval():
    assert parse_kline_push(_push("BTCUSDT", "99", 1, o=1, h=1, low=1, c=1)) == []


def test_build_subscribe_messages_batches_at_ten():
    pairs = [("BTC_USDT", Timeframe.M5)] * 12
    msgs = build_subscribe_messages(pairs)
    # 12 topics → 2 messages (10 + 2)
    assert len(msgs) == 2
    decoded = [json.loads(m) for m in msgs]
    assert decoded[0]["op"] == "subscribe"
    assert len(decoded[0]["args"]) == 10
    assert len(decoded[1]["args"]) == 2
    # Bybit uses BTCUSDT-style symbols inside topics
    assert "BTCUSDT" in decoded[0]["args"][0]
    assert decoded[0]["args"][0].startswith("kline.5.")
