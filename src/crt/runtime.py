"""Async runtime: stitches MEXC streams → store → detector → paper → TUI.

Bootstrap is done once via REST (warms each ringbuffer with the most recent
closed candles so the detector has enough lookback). After that, a single
WebSocket stream multiplexes all subscriptions and feeds closed-candle
events into the same pipeline.
"""

from __future__ import annotations

import asyncio
import logging

from crt.context import (
    SMTMonitor,
    Tier,
    candle_tier,
    passes_time_filter,
    score_signal,
    signal_aligned_with_htf,
)
from crt.data.mexc import MexcClient
from crt.data.mexc_ws import MexcWsStream
from crt.detector import CRTDetector, detect_kod, detect_model1, model1_to_signal
from crt.models import Candle, PositionStatus, Signal, Timeframe
from crt.paper import PaperEngine
from crt.smc import compute as compute_smc
from crt.store import CandleStore
from crt.tui import Dashboard

log = logging.getLogger(__name__)

BOOTSTRAP_CANDLES = 200


class Runtime:
    def __init__(
        self,
        symbols: list[str],
        timeframes: list[Timeframe],
        engine: PaperEngine,
        store: CandleStore | None = None,
        *,
        min_tier: Tier = Tier.MEDIUM,
        require_htf_alignment: bool = False,
        min_confluence: float = float("-inf"),
    ):
        self.symbols = symbols
        self.timeframes = timeframes
        self.store = store or CandleStore()
        self.engine = engine
        self.detector = CRTDetector(self.store)
        self.min_tier = min_tier
        self.require_htf_alignment = require_htf_alignment
        self.min_confluence = min_confluence
        self.smt = SMTMonitor(self.store)
        self.dashboard = Dashboard(
            self.store,
            self.engine,
            watch=[(s, t) for s in symbols for t in timeframes],
        )

    # ---------------------------------------------------------------- public

    async def bootstrap(self, client: MexcClient) -> None:
        """Fill the ringbuffer with recent history before live stream starts."""
        async def _one(sym: str, tf: Timeframe) -> None:
            try:
                kl = await client.fetch_klines(sym, tf, limit=BOOTSTRAP_CANDLES)
            except Exception:
                log.exception("bootstrap failed for %s %s", sym, tf.value)
                return
            for c in kl:
                self.store.append(c)
        tasks = [_one(s, tf) for s in self.symbols for tf in self.timeframes]
        # Stagger to avoid hammering REST rate limit.
        for i in range(0, len(tasks), 10):
            await asyncio.gather(*tasks[i:i + 10], return_exceptions=True)
        log.info("bootstrap complete: %d symbols × %d tfs", len(self.symbols), len(self.timeframes))

    def on_candle(self, candle: Candle) -> None:
        self.store.append(candle)
        for closed in self.engine.on_candle(candle):
            log.info("position closed: %s status=%s", closed.signal.symbol, closed.status.value)
        # KOD: tighten stops on open positions when a final-TS confirmation prints.
        self._check_kod_for_open_positions(candle.symbol, candle.tf)
        # Time-window gate: don't waste cycles on low-tier candles unless the
        # operator has dialed the threshold all the way down.
        if not passes_time_filter(candle, min_tier=self.min_tier):
            return
        # Collect signals from BOTH the CRT subtype state machine and the
        # orthogonal Model #1 detector.
        raw: list[Signal] = list(self.detector.evaluate(candle.symbol, candle.tf))
        window = self.store.get(candle.symbol, candle.tf)
        for m1 in detect_model1(window):
            # Skip if we already emitted a Model #1 signal for this trigger
            # candle on a prior tick.
            if any(
                s.subtype.value == "model_1_single_trigger"
                and s.detected_at == m1.detected_at
                for s in self.dashboard.recent_signals
            ):
                continue
            raw.append(model1_to_signal(m1))
        if not raw:
            return
        snap = compute_smc(window)
        for sig in raw:
            if not self._accept_signal(sig, snap):
                continue
            self.dashboard.push_signal(sig)
            self.engine.on_signal(sig)

    def _check_kod_for_open_positions(self, symbol: str, tf: Timeframe) -> None:
        for pos in self.engine.open_positions:
            if pos.signal.symbol != symbol or pos.signal.tf != tf:
                continue
            if pos.status not in (PositionStatus.OPEN, PositionStatus.TP1):
                continue
            if any(n.startswith("KOD") for n in pos.notes):
                continue
            window = self.store.get(symbol, tf)
            after = [c for c in window if c.open_time > pos.signal.detected_at]
            kod = detect_kod(pos.signal, after)
            if kod is None:
                continue
            old_stop = pos.stop_loss
            pos.stop_loss = pos.entry_price  # break-even
            pos.notes.append(
                f"KOD confirmed @ {kod.detected_at.isoformat()} — "
                f"stop {old_stop:.6f} → {pos.entry_price:.6f} (break-even)"
            )
            log.info("KOD confirmed %s %s: stop moved to break-even",
                     symbol, tf.value)

    def _accept_signal(self, sig: Signal, snap) -> bool:
        tier = candle_tier(self.store.latest(sig.symbol, sig.tf))
        sig.note = f"tier={tier.value}; {sig.note}".strip("; ")
        if not signal_aligned_with_htf(
            self.store, sig.symbol, sig.tf, sig.direction,
            require=self.require_htf_alignment,
        ):
            log.debug("signal rejected (HTF disagree): %s %s %s",
                      sig.symbol, sig.tf.value, sig.direction.value)
            return False
        score = score_signal(sig, self.store, snap, self.smt)
        sig.confluence_score = score.total
        sig.confluence_breakdown = dict(score.components)
        if sig.confluence_score < self.min_confluence:
            log.debug("signal rejected (confluence %.1f < %.1f): %s %s",
                      sig.confluence_score, self.min_confluence,
                      sig.symbol, sig.tf.value)
            return False
        return True

    async def run(self) -> None:
        async with MexcClient() as client:
            await self.bootstrap(client)

        pairs = [(s, tf) for s in self.symbols for tf in self.timeframes]
        async with MexcWsStream(pairs) as stream, self.dashboard.live() as live:
            consumer = asyncio.create_task(self._consume(stream))
            try:
                while not consumer.done():
                    live.update(self.dashboard.render(), refresh=True)
                    await asyncio.sleep(0.5)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)

    # --------------------------------------------------------------- private

    async def _consume(self, stream: MexcWsStream) -> None:
        async for candle in stream:
            self.on_candle(candle)
