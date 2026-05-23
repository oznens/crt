"""MEXC futures market data client.

REST: https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval=...
WS endpoint planned: wss://contract.mexc.com/edge (kline channel).

For the MVP we use REST polling per (symbol, tf) on a closed-candle cadence.
WebSocket streaming will be added in a follow-up — the public interface here
(`stream_closed_candles`) is async-iterator shaped so the consumer doesn't
care which transport is used underneath.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from crt.models import Candle, Timeframe

log = logging.getLogger(__name__)

REST_BASE = "https://contract.mexc.com"
KLINE_PATH = "/api/v1/contract/kline/{symbol}"
TICKER_PATH = "/api/v1/contract/ticker"

# MEXC interval codes per their docs.
_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "Min1",
    Timeframe.M5: "Min5",
    Timeframe.M15: "Min15",
    Timeframe.M30: "Min30",
    Timeframe.H1: "Min60",
    Timeframe.H4: "Hour4",
    Timeframe.D1: "Day1",
    Timeframe.W1: "Week1",
}


def _normalize_symbol(symbol: str) -> str:
    """Accept 'BTCUSDT' or 'BTC/USDT' style and emit MEXC's 'BTC_USDT'."""
    s = symbol.upper().replace("/", "_")
    if "_" not in s and s.endswith("USDT"):
        s = f"{s[:-4]}_USDT"
    return s


def _parse_kline_row(symbol: str, tf: Timeframe, row: list) -> Candle:
    # MEXC contract kline row: [t, o, c, h, l, vol, amount]
    # NB: column order differs from spot — close is index 2, high index 3.
    ts, o, c, h, low, vol, _amount = row
    return Candle(
        symbol=symbol,
        tf=tf,
        open_time=datetime.fromtimestamp(int(ts), tz=timezone.utc),
        open=float(o),
        high=float(h),
        low=float(low),
        close=float(c),
        volume=float(vol),
        closed=True,
    )


class MexcClient:
    """Async client for MEXC perpetual futures market data."""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "MexcClient":
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def fetch_top_symbols(self, limit: int = 50, quote: str = "USDT") -> list[str]:
        """Return the top-`limit` `_<quote>` perp symbols ranked by 24h amount.

        Uses /api/v1/contract/ticker which returns one entry per contract with
        `amount24` (24h quote-volume) and `volume24` (24h base-volume).
        """
        assert self._session is not None, "use MexcClient as async context manager"
        url = REST_BASE + TICKER_PATH
        async with self._session.get(url, timeout=15) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"MEXC ticker error: {payload}")
        suffix = f"_{quote.upper()}"
        rows = [r for r in payload["data"] if r.get("symbol", "").endswith(suffix)]
        # `amount24` is quote-volume; if missing, fall back to base volume.
        def _key(row: dict) -> float:
            for k in ("amount24", "amount", "volume24", "volume"):
                v = row.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return 0.0
        rows.sort(key=_key, reverse=True)
        return [r["symbol"] for r in rows[:limit]]

    async def fetch_klines(
        self,
        symbol: str,
        tf: Timeframe,
        limit: int = 200,
    ) -> list[Candle]:
        """Fetch the most recent `limit` closed candles for a symbol/timeframe."""
        assert self._session is not None, "use MexcClient as async context manager"
        norm = _normalize_symbol(symbol)
        url = REST_BASE + KLINE_PATH.format(symbol=norm)
        params = {"interval": _INTERVAL_MAP[tf]}
        async with self._session.get(url, params=params, timeout=15) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"MEXC kline error: {payload}")
        data = payload["data"]
        # MEXC returns parallel arrays: time[], open[], close[], high[], low[], vol[], amount[].
        rows = list(zip(
            data["time"], data["open"], data["close"], data["high"],
            data["low"], data["vol"], data["amount"], strict=False,
        ))
        candles = [_parse_kline_row(norm, tf, list(r)) for r in rows[-limit:]]
        return candles

    async def stream_closed_candles(
        self,
        symbol: str,
        tf: Timeframe,
        bootstrap: int = 200,
    ) -> AsyncIterator[Candle]:
        """Yield each newly-closed candle in chronological order.

        Bootstraps with the last `bootstrap` historical candles, then polls
        every (tf.seconds / 4) seconds for new closures.
        """
        history = await self.fetch_klines(symbol, tf, limit=bootstrap)
        for c in history:
            yield c

        last_ts = history[-1].open_time if history else None
        poll = max(5, tf.seconds // 4)
        while True:
            try:
                latest = await self.fetch_klines(symbol, tf, limit=3)
            except Exception:
                log.exception("MEXC poll failed for %s %s", symbol, tf)
                await asyncio.sleep(poll)
                continue
            for c in latest:
                if last_ts is None or c.open_time > last_ts:
                    yield c
                    last_ts = c.open_time
            await asyncio.sleep(poll)
