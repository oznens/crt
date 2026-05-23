"""Async runtime: stitches MEXC streams → store → detector → paper → TUI."""

from __future__ import annotations

import asyncio
import logging

from crt.data.mexc import MexcClient
from crt.detector import CRTDetector
from crt.models import Candle, Timeframe
from crt.paper import PaperEngine
from crt.store import CandleStore
from crt.tui import Dashboard

log = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self,
        symbols: list[str],
        timeframes: list[Timeframe],
        engine: PaperEngine,
        store: CandleStore | None = None,
    ):
        self.symbols = symbols
        self.timeframes = timeframes
        self.store = store or CandleStore()
        self.engine = engine
        self.detector = CRTDetector(self.store)
        self.dashboard = Dashboard(
            self.store,
            self.engine,
            watch=[(s, t) for s in symbols for t in timeframes],
        )

    async def _stream_one(self, client: MexcClient, symbol: str, tf: Timeframe) -> None:
        async for candle in client.stream_closed_candles(symbol, tf):
            self._on_candle(candle)

    def _on_candle(self, candle: Candle) -> None:
        self.store.append(candle)
        # paper updates first so a fresh candle can close a stop before we re-detect
        for closed in self.engine.on_candle(candle):
            log.info("position closed: %s status=%s", closed.signal.symbol, closed.status.value)
        signals = self.detector.evaluate(candle.symbol, candle.tf)
        for sig in signals:
            self.dashboard.push_signal(sig)
            self.engine.on_signal(sig)

    async def run(self) -> None:
        async with MexcClient() as client:
            tasks = [
                asyncio.create_task(self._stream_one(client, s, tf))
                for s in self.symbols
                for tf in self.timeframes
            ]
            with self.dashboard.live() as live:
                try:
                    while True:
                        live.update(self.dashboard.render(), refresh=True)
                        await asyncio.sleep(0.5)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass
                finally:
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
