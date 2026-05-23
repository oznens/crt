"""Async runtime: stitches Bybit streams → store → detector → paper → TUI.

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
from crt.data.bybit import BybitClient
from crt.data.bybit_ws import BybitTickerStream, BybitWsStream
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
        require_smc_grounding: bool = True,
        web_dashboard=None,
    ):
        self.symbols = symbols
        self.timeframes = timeframes
        self.store = store or CandleStore()
        self.engine = engine
        self.detector = CRTDetector(self.store)
        self.min_tier = min_tier
        self.require_htf_alignment = require_htf_alignment
        self.min_confluence = min_confluence
        self.require_smc_grounding = require_smc_grounding
        self.smt = SMTMonitor(self.store)
        self.dashboard = Dashboard(
            self.store,
            self.engine,
            watch=[(s, t) for s in symbols for t in timeframes],
        )
        # Optional web dashboard mirrors the same signals + positions feed.
        self.web_dashboard = web_dashboard

    # ---------------------------------------------------------------- public

    async def bootstrap(self, client: BybitClient) -> None:
        """Fetch history per (symbol, tf) then REPLAY the candles through
        the same on_candle() pipeline the live stream uses.

        The replay is critical: it means any CRT setups that printed
        historically also get marked-to-market against the candles that
        came after them. Positions that would have been stopped or
        target-hit historically are closed during bootstrap; only
        signals whose trade is still in flight at the end of history
        remain "open" when the WS feed takes over.

        Without this replay the live stream would emit a flood of stale
        signals against the historical buffer the moment it connected,
        opening positions at prices the market left behind hours ago.
        """
        all_candles: list[Candle] = []
        async def _fetch(sym: str, tf: Timeframe) -> None:
            try:
                kl = await client.fetch_klines(sym, tf, limit=BOOTSTRAP_CANDLES)
                all_candles.extend(kl)
            except Exception:
                log.exception("bootstrap failed for %s %s", sym, tf.value)

        tasks = [_fetch(s, tf) for s in self.symbols for tf in self.timeframes]
        # Stagger to avoid hammering REST rate limit.
        for i in range(0, len(tasks), 10):
            await asyncio.gather(*tasks[i:i + 10], return_exceptions=True)

        # Replay chronologically across all symbols and TFs.
        all_candles.sort(key=lambda c: (c.open_time, c.tf.seconds))
        log.info("bootstrap replay: %d candles across %d symbols × %d tfs",
                 len(all_candles), len(self.symbols), len(self.timeframes))
        for c in all_candles:
            self.on_candle(c)
        log.info(
            "bootstrap complete: %d open, %d closed positions, %d signals",
            len(self.engine.open_positions),
            len(self.engine.closed_positions),
            sum(1 for _ in self.dashboard.recent_signals),
        )

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
            # Pass the current candle so the paper engine only opens
            # positions whose entry was actually reachable on the
            # candle that triggered the signal — prevents the "ghost
            # open position at stale historical price" bug.
            pos = self.engine.on_signal(sig, fill_candle=candle)
            if pos is None:
                continue
            self.dashboard.push_signal(sig)
            if self.web_dashboard is not None:
                self.web_dashboard.push_signal(sig)

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
        if self.require_smc_grounding:
            # Hard prerequisite: a CRT must sit on real SMC context. A
            # signal whose only positive contributors are time tier + HTF
            # alignment is just a candle pattern in the middle of nowhere.
            smc_grounded = any(
                k in score.components
                for k in ("fvg_aligned", "ob_aligned", "bos_aligned",
                          "liquidity_swept", "smt_aligned")
            )
            if not smc_grounded:
                log.debug("signal rejected (no SMC context): %s %s",
                          sig.symbol, sig.tf.value)
                return False
        if sig.confluence_score < self.min_confluence:
            log.debug("signal rejected (confluence %.1f < %.1f): %s %s",
                      sig.confluence_score, self.min_confluence,
                      sig.symbol, sig.tf.value)
            return False
        return True

    async def run(self) -> None:
        async with BybitClient() as client:
            await self.bootstrap(client)

        pairs = [(s, tf) for s in self.symbols for tf in self.timeframes]
        async with (
            BybitWsStream(pairs) as kline_stream,
            BybitTickerStream(self.symbols) as ticker_stream,
            self.dashboard.live() as live,
        ):
            kline_task = asyncio.create_task(self._consume_klines(kline_stream))
            tick_task = asyncio.create_task(self._consume_ticks(ticker_stream))
            try:
                while not (kline_task.done() and tick_task.done()):
                    live.update(self.dashboard.render(), refresh=True)
                    await asyncio.sleep(0.5)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                kline_task.cancel()
                tick_task.cancel()
                await asyncio.gather(kline_task, tick_task, return_exceptions=True)

    async def run_headless(self) -> None:
        """Run the data → detector → paper pipeline without the Rich TUI.

        Spawns BOTH the kline stream (detector + paper engine) AND the
        ticker stream (intra-candle uPnL + SL/TP tripwires) so the web
        dashboard sees live PnL between candle closes.
        """
        async with BybitClient() as client:
            await self.bootstrap(client)
        pairs = [(s, tf) for s in self.symbols for tf in self.timeframes]
        async with (
            BybitWsStream(pairs) as kline_stream,
            BybitTickerStream(self.symbols) as ticker_stream,
        ):
            await asyncio.gather(
                self._consume_klines(kline_stream),
                self._consume_ticks(ticker_stream),
            )

    # --------------------------------------------------------------- private

    async def _consume_klines(self, stream: BybitWsStream) -> None:
        async for candle in stream:
            self.on_candle(candle)

    async def _consume_ticks(self, stream: BybitTickerStream) -> None:
        """Forward every ticker push into the paper engine for live uPnL
        and intra-candle SL/TP. Ticker fires ~once per second per symbol;
        the engine call is cheap enough to handle that cadence."""
        async for symbol, price in stream:
            self.engine.on_tick(symbol, price)
            # Update web dashboard's last-price cache (if mounted) so the
            # watchlist shows live prices, not stale candle closes.
            if self.web_dashboard is not None:
                self.web_dashboard.on_tick(symbol, price)
