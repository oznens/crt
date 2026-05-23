"""MEXC perpetual-futures WebSocket stream.

Endpoint: wss://contract.mexc.com/edge

Subscription per (symbol, interval):
    {"method":"sub.kline","param":{"symbol":"BTC_USDT","interval":"Min15"}}

Each push (`channel == "push.kline"`) updates the CURRENT forming candle.
We translate the stream into closed-candle events by detecting timestamp
rollovers per (symbol, tf): whenever we see a new `t` for a key we already
have a buffered candle for, the previous one is finalized and emitted.

Heartbeat: client sends `{"method":"ping"}` every 15s; server returns
`{"method":"pong"}`. No application-level reply needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import websockets

from crt.models import Candle, Timeframe

log = logging.getLogger(__name__)

WS_URL = "wss://contract.mexc.com/edge"

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
_REVERSE_INTERVAL: dict[str, Timeframe] = {v: k for k, v in _INTERVAL_MAP.items()}

HEARTBEAT_SECONDS = 15
RECONNECT_BACKOFF_INITIAL = 2.0
RECONNECT_BACKOFF_MAX = 60.0


def parse_kline_push(msg: dict) -> tuple[Candle, bool] | None:
    """Parse a MEXC `push.kline` payload.

    Returns (candle, is_partial). is_partial=True means it's a snapshot of
    the still-forming candle; False means the candle is closed (a new t
    has been seen). Returns None if the message isn't a kline push.
    """
    if msg.get("channel") != "push.kline":
        return None
    data = msg.get("data") or {}
    interval = data.get("interval")
    tf = _REVERSE_INTERVAL.get(interval)
    if tf is None:
        return None
    symbol = data.get("symbol")
    ts_open = data.get("t")
    if symbol is None or ts_open is None:
        return None
    candle = Candle(
        symbol=symbol,
        tf=tf,
        open_time=datetime.fromtimestamp(int(ts_open), tz=timezone.utc),
        open=float(data.get("o", 0.0)),
        high=float(data.get("h", 0.0)),
        low=float(data.get("l", 0.0)),
        close=float(data.get("c", 0.0)),
        volume=float(data.get("q") or data.get("a") or 0.0),
        closed=False,
    )
    return candle, True


class _CloseDetector:
    """Track the latest open_time per (symbol, tf) and emit closes on rollover."""

    def __init__(self) -> None:
        self._latest: dict[tuple[str, Timeframe], Candle] = {}

    def feed(self, candle: Candle) -> Candle | None:
        """Update internal state. Returns the *previous* candle as closed
        if this update started a new bar; otherwise None."""
        key = (candle.symbol, candle.tf)
        prev = self._latest.get(key)
        if prev is None:
            self._latest[key] = candle
            return None
        if candle.open_time > prev.open_time:
            # Previous candle has closed — emit it with closed=True.
            closed = Candle(
                symbol=prev.symbol, tf=prev.tf, open_time=prev.open_time,
                open=prev.open, high=prev.high, low=prev.low,
                close=prev.close, volume=prev.volume, closed=True,
            )
            self._latest[key] = candle
            return closed
        # Same bar — replace with the more recent snapshot.
        self._latest[key] = candle
        return None


def build_subscribe_messages(
    pairs: list[tuple[str, Timeframe]],
) -> list[str]:
    """Return the JSON payloads to subscribe to each (symbol, tf)."""
    out: list[str] = []
    for symbol, tf in pairs:
        out.append(json.dumps({
            "method": "sub.kline",
            "param": {"symbol": symbol, "interval": _INTERVAL_MAP[tf]},
        }))
    return out


class MexcWsStream:
    """Open one WS connection, multiplex all subscriptions, emit closed candles.

    Use as an async context manager + async iterator:

        async with MexcWsStream(pairs) as stream:
            async for candle in stream:
                ...
    """

    def __init__(self, pairs: list[tuple[str, Timeframe]]):
        self.pairs = pairs
        self._queue: asyncio.Queue[Candle] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._detector = _CloseDetector()
        self._stop = asyncio.Event()

    async def __aenter__(self) -> "MexcWsStream":
        self._tasks.append(asyncio.create_task(self._run()))
        return self

    async def __aexit__(self, *exc) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def __aiter__(self) -> AsyncIterator[Candle]:
        return self

    async def __anext__(self) -> Candle:
        return await self._queue.get()

    # -------------------------------------------------------------- internal

    async def _run(self) -> None:
        backoff = RECONNECT_BACKOFF_INITIAL
        while not self._stop.is_set():
            try:
                async with websockets.connect(WS_URL, ping_interval=None) as ws:
                    log.info("MEXC WS connected: %d subscriptions", len(self.pairs))
                    backoff = RECONNECT_BACKOFF_INITIAL
                    await self._subscribe(ws)
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MEXC WS connection failed; backing off %.1fs", backoff)
            if self._stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)

    async def _subscribe(self, ws: Any) -> None:
        for payload in build_subscribe_messages(self.pairs):
            await ws.send(payload)

    async def _read_loop(self, ws: Any) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(ws))
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("method") == "pong":
                    continue
                parsed = parse_kline_push(msg)
                if parsed is None:
                    continue
                candle, _partial = parsed
                closed = self._detector.feed(candle)
                if closed is not None:
                    await self._queue.put(closed)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, ws: Any) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await ws.send(json.dumps({"method": "ping"}))
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("MEXC WS heartbeat failed")
