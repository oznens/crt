"""Unit tests for BybitClient — fake aiohttp session, no network."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from crt.data.bybit import (
    BybitClient,
    _bybit_symbol,
    _canonical_symbol,
)
from crt.models import Timeframe


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple[str, dict | None]] = []

    @asynccontextmanager
    async def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        yield _FakeResp(self.payload)

    async def close(self):
        pass


def test_symbol_conversions_round_trip():
    assert _bybit_symbol("BTC_USDT") == "BTCUSDT"
    assert _bybit_symbol("BTC/USDT") == "BTCUSDT"
    assert _bybit_symbol("BTCUSDT") == "BTCUSDT"
    assert _canonical_symbol("BTCUSDT") == "BTC_USDT"
    assert _canonical_symbol("ETHUSDC") == "ETH_USDC"
    # Symbol without a known quote falls through unchanged.
    assert _canonical_symbol("XYZ") == "XYZ"


def test_fetch_top_symbols_ranks_by_turnover_and_filters_quote():
    payload = {
        "retCode": 0,
        "result": {"list": [
            {"symbol": "DOGEUSDT", "turnover24h": "5"},
            {"symbol": "BTCUSDT", "turnover24h": "100"},
            {"symbol": "ETHUSDT", "turnover24h": "50"},
            {"symbol": "SOLUSDT", "turnover24h": "20"},
            {"symbol": "BTCUSDC", "turnover24h": "9999"},  # wrong quote
            {"symbol": "XRPUSDT"},  # no volume → ranked last
        ]},
    }
    client = BybitClient(session=_FakeSession(payload))

    async def run():
        return await client.fetch_top_symbols(limit=3, quote="USDT")

    out = asyncio.run(run())
    assert out == ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
    assert "BTC_USDC" not in out


def test_fetch_top_symbols_falls_back_to_volume24h():
    payload = {
        "retCode": 0,
        "result": {"list": [
            {"symbol": "ABCUSDT", "volume24h": "10"},
            {"symbol": "DEFUSDT", "volume24h": "30"},
            {"symbol": "GHIUSDT", "volume24h": "20"},
        ]},
    }
    client = BybitClient(session=_FakeSession(payload))

    async def run():
        return await client.fetch_top_symbols(limit=10)

    out = asyncio.run(run())
    assert out == ["DEF_USDT", "GHI_USDT", "ABC_USDT"]


def test_fetch_klines_reverses_bybit_order_to_chronological():
    # Bybit returns newest-first. The client should flip to chronological.
    payload = {
        "retCode": 0,
        "result": {"list": [
            # [startMs, o, h, l, c, vol, turnover]
            ["1700000900000", "101.5", "102", "101", "101.8", "12", "1218"],
            ["1700000600000", "100",   "101", "99.5", "101",   "10", "1010"],
            ["1700000300000", "99",    "100", "98.5", "100",   "11", "1099"],
        ]},
    }
    client = BybitClient(session=_FakeSession(payload))

    async def run():
        return await client.fetch_klines("BTC_USDT", Timeframe.M5, limit=3)

    candles = asyncio.run(run())
    assert len(candles) == 3
    # First candle in output should be the oldest (1700000300 < 1700000600 < 1700000900)
    assert candles[0].open == 99
    assert candles[1].open == 100
    assert candles[2].open == 101.5
    # Symbol is canonicalised back to underscore form
    assert candles[0].symbol == "BTC_USDT"


def test_fetch_klines_raises_on_api_error():
    client = BybitClient(session=_FakeSession({"retCode": 10001, "retMsg": "boom"}))

    async def run():
        return await client.fetch_klines("BTC_USDT", Timeframe.M5, limit=3)

    with pytest.raises(RuntimeError, match="Bybit kline error"):
        asyncio.run(run())
