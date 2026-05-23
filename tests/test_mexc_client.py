"""Unit tests for MexcClient that don't touch the network."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from crt.data.mexc import MexcClient


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


class _FakeSession:
    """Drop-in replacement for aiohttp.ClientSession that captures URLs and
    returns a canned JSON payload."""

    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple[str, dict | None]] = []

    @asynccontextmanager
    async def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        yield _FakeResp(self.payload)

    async def close(self):
        pass


def test_fetch_top_symbols_orders_by_amount24():
    payload = {
        "success": True,
        "data": [
            {"symbol": "DOGE_USDT", "amount24": "5"},
            {"symbol": "BTC_USDT", "amount24": "100"},
            {"symbol": "ETH_USDT", "amount24": "50"},
            {"symbol": "SOL_USDT", "amount24": "20"},
            # Wrong quote → excluded
            {"symbol": "BTC_USDC", "amount24": "9999"},
            # No volume info → ranked last
            {"symbol": "XRP_USDT"},
        ],
    }
    session = _FakeSession(payload)
    client = MexcClient(session=session)

    async def run():
        return await client.fetch_top_symbols(limit=3, quote="USDT")

    out = asyncio.run(run())
    assert out == ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
    # Quote filter dropped BTC_USDC
    assert "BTC_USDC" not in out


def test_fetch_top_symbols_falls_back_to_volume_field():
    payload = {
        "success": True,
        "data": [
            {"symbol": "ABC_USDT", "volume24": "10"},
            {"symbol": "DEF_USDT", "volume24": "30"},
            {"symbol": "GHI_USDT", "volume24": "20"},
        ],
    }
    client = MexcClient(session=_FakeSession(payload))

    async def run():
        return await client.fetch_top_symbols(limit=10)

    out = asyncio.run(run())
    assert out == ["DEF_USDT", "GHI_USDT", "ABC_USDT"]


def test_fetch_top_symbols_raises_on_api_error():
    client = MexcClient(session=_FakeSession({"success": False, "msg": "boom"}))

    async def run():
        return await client.fetch_top_symbols()

    with pytest.raises(RuntimeError, match="MEXC ticker error"):
        asyncio.run(run())
