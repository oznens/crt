"""Bybit V5 public WebSocket for linear perpetual klines and tickers.

Endpoint: wss://stream.bybit.com/v5/public/linear

Topics we use:
- "kline.<interval>.<SYMBOL>": closed candle bars (confirm=True only).
- "tickers.<SYMBOL>": live last-price updates ~once per second.

Subscription:
    {"op": "subscribe", "args": ["kline.15.BTCUSDT", ...]}

Heartbeat: client-sent {"op": "ping"} every 20s. Bybit caps each
subscribe message at 10 args on the public channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import websockets

from crt.data.bybit import _bybit_symbol, _canonical_symbol
from crt.models import Candle, Timeframe

log = logging.getLogger(__name__)

WS_URL = "wss://stream.bybit.com/v5/public/linear"

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
_REVERSE_INTERVAL: dict[str, Timeframe] = {v: k for k, v in _INTERVAL_MAP.items()}

HEARTBEAT_SECONDS = 20
RECONNECT_BACKOFF_INITIAL = 2.0
RECONNECT_BACKOFF_MAX = 60.0
# Bybit caps each subscribe message at 10 topics on the public channel.
SUBSCRIBE_BATCH = 10


def parse_kline_push(msg: dict) -> list[Candle]:
    """Parse a Bybit `kline.<interval>.<symbol>` push.

    Returns a list of Candle objects. Only candles with `confirm` == True
    are returned (the in-progress candle is dropped).
    """
    topic = msg.get("topic", "")
    if not topic.startswith("kline."):
        return []
    parts = topic.split(".")
    if len(parts) < 3:
        return []
    interval = parts[1]
    symbol = parts[2]
    tf = _REVERSE_INTERVAL.get(interval)
    if tf is None:
        return []
    canonical = _canonical_symbol(symbol)
    out: list[Candle] = []
    for item in msg.get("data") or []:
        if not item.get("confirm"):
            continue
        out.append(Candle(
            symbol=canonical,
            tf=tf,
            open_time=datetime.fromtimestamp(int(item["start"]) / 1000, tz=timezone.utc),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item.get("volume", 0.0)),
            closed=True,
        ))
    return out


def build_subscribe_messages(pairs: list[tuple[str, Timeframe]]) -> list[str]:
    """Pack subscription topics into one or more `op:subscribe` payloads.

    Bybit accepts at most SUBSCRIBE_BATCH topics per message, so for
    large universes (50+ symbols × multiple TFs) we issue multiple
    messages.
    """
    topics = [f"kline.{_INTERVAL_MAP[tf]}.{_bybit_symbol(sym)}" for sym, tf in pairs]
    out: list[str] = []
    for i in range(0, len(topics), SUBSCRIBE_BATCH):
        chunk = topics[i: i + SUBSCRIBE_BATCH]
        out.append(json.dumps({"op": "subscribe", "args": chunk}))
    return out


def build_ticker_subscribe_messages(symbols: list[str]) -> list[str]:
    """Pack `tickers.<SYMBOL>` topic subscriptions in 10-arg batches."""
    topics = [f"tickers.{_bybit_symbol(s)}" for s in symbols]
    out: list[str] = []
    for i in range(0, len(topics), SUBSCRIBE_BATCH):
        chunk = topics[i: i + SUBSCRIBE_BATCH]
        out.append(json.dumps({"op": "subscribe", "args": chunk}))
    return out


def parse_ticker_push(msg: dict) -> tuple[str, float] | None:
    """Parse a Bybit `tickers.<SYMBOL>` push.

    Returns (canonical_symbol, last_price) or None if the message isn't
    a ticker push or has no last-price field. Bybit pushes both full
    snapshots (`type == "snapshot"`) and partial deltas; we only need
    the last-price field which appears in both.
    """
    topic = msg.get("topic", "")
    if not topic.startswith("tickers."):
        return None
    sym = topic.split(".", 1)[1]
    data = msg.get("data") or {}
    last = data.get("lastPrice") or data.get("markPrice") or data.get("indexPrice")
    if last is None:
        return None
    try:
        return _canonical_symbol(sym), float(last)
    except (TypeError, ValueError):
        return None


class BybitWsStream:
    """One WS connection, multiplex all (symbol, tf) subscriptions, emit
    only closed candles.

    Use as an async context manager + async iterator:

        async with BybitWsStream(pairs) as stream:
            async for candle in stream:
                ...
    """

    def __init__(self, pairs: list[tuple[str, Timeframe]]):
        self.pairs = pairs
        self._queue: asyncio.Queue[Candle] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def __aenter__(self) -> "BybitWsStream":
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
                    log.info("Bybit WS connected: %d subscriptions", len(self.pairs))
                    backoff = RECONNECT_BACKOFF_INITIAL
                    await self._subscribe(ws)
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Bybit WS connection failed; backing off %.1fs", backoff)
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
                # ack / pong messages can be ignored
                if msg.get("op") in ("subscribe", "pong"):
                    continue
                if msg.get("ret_msg") == "pong":
                    continue
                for candle in parse_kline_push(msg):
                    await self._queue.put(candle)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, ws: Any) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await ws.send(json.dumps({"op": "ping"}))
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Bybit WS heartbeat failed")

class BybitTickerStream:
    '''One WS connection, multiplex tickers for many symbols, emit (sym, price)
    tuples whenever Bybit pushes a last-price update (~1/s/symbol).

    Use as an async context manager + async iterator:

        async with BybitTickerStream(['BTC_USDT', 'ETH_USDT']) as t:
            async for symbol, price in t:
                ...
    '''

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self._queue: asyncio.Queue[tuple[str, float]] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def __aenter__(self) -> 'BybitTickerStream':
        self._tasks.append(asyncio.create_task(self._run()))
        return self

    async def __aexit__(self, *exc) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def __aiter__(self) -> AsyncIterator[tuple[str, float]]:
        return self

    async def __anext__(self) -> tuple[str, float]:
        return await self._queue.get()

    async def _run(self) -> None:
        backoff = RECONNECT_BACKOFF_INITIAL
        while not self._stop.is_set():
            try:
                async with websockets.connect(WS_URL, ping_interval=None) as ws:
                    log.info('Bybit ticker WS connected: %d symbols', len(self.symbols))
                    backoff = RECONNECT_BACKOFF_INITIAL
                    for payload in build_ticker_subscribe_messages(self.symbols):
                        await ws.send(payload)
                    heartbeat = asyncio.create_task(self._heartbeat(ws))
                    try:
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if msg.get('op') in ('subscribe', 'pong'):
                                continue
                            if msg.get('ret_msg') == 'pong':
                                continue
                            parsed = parse_ticker_push(msg)
                            if parsed is not None:
                                await self._queue.put(parsed)
                    finally:
                        heartbeat.cancel()
                        await asyncio.gather(heartbeat, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('Bybit ticker WS failed; backing off %.1fs', backoff)
            if self._stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)

    async def _heartbeat(self, ws: Any) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await ws.send(json.dumps({'op': 'ping'}))
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception('Bybit ticker WS heartbeat failed')

