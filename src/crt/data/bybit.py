"""Bybit V5 public market data client (linear USDT perpetuals).

REST endpoints:
  GET https://api.bybit.com/v5/market/kline
  GET https://api.bybit.com/v5/market/tickers?category=linear

Kline rows arrive reverse-chronological (newest first), so we reverse
them before yielding into the pipeline.

We canonicalise symbols to the underscore form `BTC_USDT` everywhere in
the codebase. Inside this client we translate to / from Bybit's
underscoreless `BTCUSDT` form transparently.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from crt.models import Candle, Timeframe

log = logging.getLogger(__name__)

REST_BASE = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"
TICKERS_PATH = "/v5/market/tickers"

# Bybit interval codes per their docs.
_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1",
    Timeframe.M5: "5",
    Timeframe.M15: "15",
    Timeframe.M30: "30",
    Timeframe.H1: "60",
    Timeframe.H4: "240",
    Timeframe.D1: "D",
    Timeframe.W1: "W",
}


def _bybit_symbol(symbol: str) -> str:
    """Convert our canonical `BTC_USDT` to Bybit's `BTCUSDT`."""
    return symbol.replace("_", "").replace("/", "").upper()


def _canonical_symbol(bybit_symbol: str) -> str:
    """Convert Bybit's `BTCUSDT` back to our canonical `BTC_USDT`.

    The split is heuristic — for the USDT, USDC, USD, BTC quotes that
    cover virtually every Bybit linear contract, splitting on the quote
    suffix recovers the right shape.
    """
    s = bybit_symbol.upper()
    for quote in ("USDT", "USDC", "USD", "BTC"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[:-len(quote)]}_{quote}"
    return s


def _parse_kline_row(symbol: str, tf: Timeframe, row: list) -> Candle:
    # [startMs, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
    start_ms, o, h, low, c, vol, _turnover = row
    return Candle(
        symbol=symbol,
        tf=tf,
        open_time=datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc),
        open=float(o),
        high=float(h),
        low=float(low),
        close=float(c),
        volume=float(vol),
        closed=True,
    )


class BybitClient:
    """Async client for Bybit V5 linear perpetual market data."""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "BybitClient":
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def fetch_klines(
        self,
        symbol: str,
        tf: Timeframe,
        limit: int = 200,
    ) -> list[Candle]:
        """Fetch the most recent `limit` closed candles for a symbol/timeframe."""
        assert self._session is not None, "use BybitClient as async context manager"
        params = {
            "category": "linear",
            "symbol": _bybit_symbol(symbol),
            "interval": _INTERVAL_MAP[tf],
            "limit": min(limit, 1000),
        }
        async with self._session.get(REST_BASE + KLINE_PATH, params=params, timeout=15) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit kline error: {payload}")
        rows = payload["result"]["list"]
        # Bybit returns newest-first; flip so the consumer sees chronological order.
        canonical = symbol if "_" in symbol else _canonical_symbol(symbol)
        return [_parse_kline_row(canonical, tf, row) for row in reversed(rows)]

    async def fetch_top_symbols(self, limit: int = 50, quote: str = "USDT") -> list[str]:
        """Return the top `limit` linear perp symbols by 24h turnover.

        We use turnover (quote-asset notional volume) since it's the most
        meaningful liquidity proxy across symbols with different prices.
        """
        assert self._session is not None, "use BybitClient as async context manager"
        params = {"category": "linear"}
        async with self._session.get(REST_BASE + TICKERS_PATH, params=params, timeout=15) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit ticker error: {payload}")
        rows = payload["result"]["list"]
        suffix = quote.upper()
        rows = [r for r in rows if r.get("symbol", "").endswith(suffix)]

        def _key(row: dict) -> float:
            for k in ("turnover24h", "volume24h"):
                v = row.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return 0.0
        rows.sort(key=_key, reverse=True)
        return [_canonical_symbol(r["symbol"]) for r in rows[:limit]]

    async def stream_closed_candles(
        self,
        symbol: str,
        tf: Timeframe,
        bootstrap: int = 200,
    ) -> AsyncIterator[Candle]:
        """REST-polling fallback for live streaming. Use BybitWsStream for WS."""
        history = await self.fetch_klines(symbol, tf, limit=bootstrap)
        for c in history:
            yield c

        last_ts = history[-1].open_time if history else None
        poll = max(5, tf.seconds // 4)
        while True:
            try:
                latest = await self.fetch_klines(symbol, tf, limit=3)
            except Exception:
                log.exception("Bybit poll failed for %s %s", symbol, tf.value)
                await asyncio.sleep(poll)
                continue
            for c in latest:
                if last_ts is None or c.open_time > last_ts:
                    yield c
                    last_ts = c.open_time
            await asyncio.sleep(poll)
