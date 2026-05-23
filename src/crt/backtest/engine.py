"""Replay historical candles through the same detector + paper engine
that the live runtime uses.

Two ways to seed candles:

1. `load_from_exchange(...)` — pull a window of klines via the REST endpoint
   and replay them in chronological order.
2. `load_from_iterable(candles)` — feed any sequence of `Candle` objects.
   Useful for tests, fixture-based scenarios, or off-exchange data.

The runner reuses `CandleStore`, `CRTDetector`, and `PaperEngine` so the
backtest produces results identical to what the live scanner would,
modulo the absence of partial candles.
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from crt.context import (
    SMTMonitor,
    Tier,
    candle_tier,
    passes_time_filter,
    score_signal,
    signal_aligned_with_htf,
)
from crt.data.bybit import BybitClient
from crt.detector import CRTDetector, detect_kod, detect_model1, model1_to_signal
from crt.models import (
    Candle,
    CRTSubtype,
    Direction,
    PaperPosition,
    PositionStatus,
    Signal,
    Timeframe,
)
from crt.paper import FailureMode, PaperConfig, PaperEngine, classify as classify_failure
from crt.smc import compute as compute_smc
from crt.store import CandleStore


@dataclass(slots=True)
class BacktestReport:
    """Summary metrics emitted at the end of a backtest run."""

    symbols: list[str]
    timeframes: list[Timeframe]
    starting_balance: float
    ending_balance: float
    signals: list[Signal]
    positions: list[PaperPosition]
    failure_breakdown: dict = field(default_factory=dict)

    @property
    def total_pnl(self) -> float:
        return self.ending_balance - self.starting_balance

    @property
    def return_pct(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return self.total_pnl / self.starting_balance * 100

    @property
    def wins(self) -> int:
        return sum(1 for p in self.positions if p.status == PositionStatus.CLOSED_TP)

    @property
    def losses(self) -> int:
        return sum(1 for p in self.positions if p.status == PositionStatus.CLOSED_SL)

    @property
    def win_rate(self) -> float:
        decisive = self.wins + self.losses
        return self.wins / decisive * 100 if decisive else 0.0

    @property
    def avg_win(self) -> float:
        wins = [p.realized_pnl for p in self.positions if p.realized_pnl > 0]
        return statistics.mean(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [p.realized_pnl for p in self.positions if p.realized_pnl < 0]
        return statistics.mean(losses) if losses else 0.0

    @property
    def expectancy(self) -> float:
        decisive = self.wins + self.losses
        if not decisive:
            return 0.0
        win_p = self.wins / decisive
        return win_p * self.avg_win + (1 - win_p) * self.avg_loss

    @property
    def max_drawdown(self) -> float:
        """Maximum peak-to-trough drop on the equity curve."""
        equity = self.starting_balance
        peak = equity
        worst = 0.0
        # Order positions by close time so the curve is monotonic in time.
        closed = sorted(
            (p for p in self.positions if p.closed_at is not None),
            key=lambda p: p.closed_at,
        )
        for p in closed:
            equity += p.realized_pnl
            peak = max(peak, equity)
            worst = min(worst, equity - peak)
        return worst

    @property
    def avg_confluence(self) -> float:
        if not self.signals:
            return 0.0
        return statistics.mean(s.confluence_score for s in self.signals)

    def by_confluence_bucket(self) -> dict[str, dict]:
        """Bucket positions by confluence score so we can see if higher
        confluence actually correlates with better realized PnL."""
        buckets: dict[str, dict] = {}
        for p in self.positions:
            score = p.signal.confluence_score
            if score <= 0:
                key = "≤0"
            elif score <= 3:
                key = "1–3"
            elif score <= 6:
                key = "4–6"
            else:
                key = "≥7"
            b = buckets.setdefault(
                key, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
            )
            b["trades"] += 1
            b["pnl"] += p.realized_pnl
            if p.status == PositionStatus.CLOSED_TP:
                b["wins"] += 1
            elif p.status == PositionStatus.CLOSED_SL:
                b["losses"] += 1
        return buckets

    def by_failure_mode(
        self,
        store: CandleStore,
        smt,
    ) -> dict[FailureMode, dict]:
        """Bucket SL-closed positions by Episode-8 failure mode."""
        agg: dict[FailureMode, dict] = {}
        for p in self.positions:
            if p.status != PositionStatus.CLOSED_SL:
                continue
            tag = classify_failure(p, store, smt)
            b = agg.setdefault(tag.mode, {"trades": 0, "pnl": 0.0})
            b["trades"] += 1
            b["pnl"] += p.realized_pnl
        return agg

    def by_subtype(self) -> dict[CRTSubtype, dict]:
        """Win-rate breakdown per CRT subtype."""
        agg: dict[CRTSubtype, dict] = {}
        for p in self.positions:
            bucket = agg.setdefault(
                p.signal.subtype,
                {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
            )
            bucket["trades"] += 1
            bucket["pnl"] += p.realized_pnl
            if p.status == PositionStatus.CLOSED_TP:
                bucket["wins"] += 1
            elif p.status == PositionStatus.CLOSED_SL:
                bucket["losses"] += 1
        return agg


@dataclass
class BacktestRunner:
    """Replay candles through detector → paper engine, collect a report."""

    symbols: list[str]
    timeframes: list[Timeframe]
    paper_config: PaperConfig = field(default_factory=PaperConfig)
    min_tier: Tier = Tier.MEDIUM
    require_htf_alignment: bool = False
    min_confluence: float = float("-inf")
    require_smc_grounding: bool = True
    store: CandleStore = field(default_factory=CandleStore)
    engine: PaperEngine = field(init=False)
    detector: CRTDetector = field(init=False)
    signals: list[Signal] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.engine = PaperEngine(self.paper_config)
        self.detector = CRTDetector(self.store)
        self.smt = SMTMonitor(self.store)

    # ------------------------------------------------------------------ feed

    def feed(self, candles: Iterable[Candle]) -> None:
        """Replay a stream of candles in chronological order."""
        # Sort defensively in case caller passed an unordered iterable.
        ordered = sorted(candles, key=lambda c: (c.open_time, c.tf.seconds))
        for candle in ordered:
            self._on_candle(candle)

    async def load_from_exchange(
        self,
        client: BybitClient,
        *,
        limit_per_tf: int = 500,
    ) -> None:
        """Bootstrap from the exchange REST: pull the most-recent N closed candles
        per (symbol, tf) and replay them through the pipeline.

        For longer windows the caller can stitch multiple calls together
        via `feed()` directly.
        """
        all_candles: list[Candle] = []
        async def _one(s: str, tf: Timeframe) -> None:
            try:
                cs = await client.fetch_klines(s, tf, limit=limit_per_tf)
                all_candles.extend(cs)
            except Exception:
                pass
        await asyncio.gather(*(_one(s, tf) for s in self.symbols for tf in self.timeframes))
        self.feed(all_candles)

    # ----------------------------------------------------------------- report

    def report(self) -> BacktestReport:
        failures: dict = {}
        positions = list(self.engine.closed_positions) + list(self.engine.open_positions)
        for p in positions:
            if p.status != PositionStatus.CLOSED_SL:
                continue
            tag = classify_failure(p, self.store, self.smt)
            b = failures.setdefault(tag.mode, {"trades": 0, "pnl": 0.0})
            b["trades"] += 1
            b["pnl"] += p.realized_pnl
        return BacktestReport(
            symbols=list(self.symbols),
            timeframes=list(self.timeframes),
            starting_balance=self.paper_config.starting_balance,
            ending_balance=self.engine.balance,
            signals=list(self.signals),
            positions=positions,
            failure_breakdown=failures,
        )

    # ---------------------------------------------------------------- private

    def _on_candle(self, candle: Candle) -> None:
        self.store.append(candle)
        for _closed in self.engine.on_candle(candle):
            pass
        self._check_kod_open_positions(candle.symbol, candle.tf)
        if not passes_time_filter(candle, min_tier=self.min_tier):
            return
        raw: list[Signal] = list(self.detector.evaluate(candle.symbol, candle.tf))
        window = self.store.get(candle.symbol, candle.tf)
        emitted_m1 = {
            (s.symbol, s.detected_at) for s in self.signals
            if s.subtype is CRTSubtype.MODEL_1
        }
        for m1 in detect_model1(window):
            if (m1.symbol, m1.detected_at) in emitted_m1:
                continue
            raw.append(model1_to_signal(m1))
        if not raw:
            return
        snap = compute_smc(window)
        for sig in raw:
            if not self._accept_signal(sig, snap):
                continue
            pos = self.engine.on_signal(sig, fill_candle=candle)
            if pos is None:
                continue
            self.signals.append(sig)

    def _check_kod_open_positions(self, symbol: str, tf: Timeframe) -> None:
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
            pos.stop_loss = pos.entry_price
            pos.notes.append(
                f"KOD confirmed @ {kod.detected_at.isoformat()} — "
                f"stop {old_stop:.6f} → {pos.entry_price:.6f} (break-even)"
            )

    def _accept_signal(self, sig: Signal, snap) -> bool:
        latest = self.store.latest(sig.symbol, sig.tf)
        if latest is None:
            return False
        tier = candle_tier(latest)
        sig.note = f"tier={tier.value}; {sig.note}".strip("; ")
        if not signal_aligned_with_htf(
            self.store, sig.symbol, sig.tf, sig.direction,
            require=self.require_htf_alignment,
        ):
            return False
        score = score_signal(sig, self.store, snap, self.smt)
        sig.confluence_score = score.total
        sig.confluence_breakdown = dict(score.components)
        if self.require_smc_grounding:
            smc_grounded = any(
                k in score.components
                for k in ("fvg_aligned", "ob_aligned", "bos_aligned",
                          "liquidity_swept", "smt_aligned")
            )
            if not smc_grounded:
                return False
        return sig.confluence_score >= self.min_confluence


def format_report(r: BacktestReport) -> str:
    """Human-readable summary, kept dependency-free for use in CLI output."""
    lines: list[str] = []
    lines.append(f"Symbols: {', '.join(r.symbols)}")
    lines.append(f"Timeframes: {', '.join(t.value for t in r.timeframes)}")
    lines.append(f"Signals: {len(r.signals)}  Positions: {len(r.positions)}")
    lines.append(f"Balance: {r.starting_balance:.2f} → {r.ending_balance:.2f} "
                 f"({r.return_pct:+.2f}%)")
    lines.append(f"Win rate: {r.win_rate:.1f}%  ({r.wins}W / {r.losses}L)")
    lines.append(f"Avg win: {r.avg_win:+.2f}  Avg loss: {r.avg_loss:+.2f}")
    lines.append(f"Expectancy/trade: {r.expectancy:+.2f}")
    lines.append(f"Max drawdown: {r.max_drawdown:+.2f}")
    lines.append(f"Avg confluence: {r.avg_confluence:+.2f}")
    breakdown = r.by_subtype()
    if breakdown:
        lines.append("")
        lines.append("By subtype:")
        for st, b in breakdown.items():
            wr = (b["wins"] / (b["wins"] + b["losses"]) * 100) if (b["wins"] + b["losses"]) else 0
            lines.append(
                f"  {st.value:<32} trades={b['trades']:<3} "
                f"W={b['wins']:<3} L={b['losses']:<3} "
                f"WR={wr:5.1f}%  pnl={b['pnl']:+.2f}"
            )
    conf = r.by_confluence_bucket()
    if conf:
        lines.append("")
        lines.append("By confluence:")
        for bucket, b in sorted(conf.items()):
            wr = (b["wins"] / (b["wins"] + b["losses"]) * 100) if (b["wins"] + b["losses"]) else 0
            lines.append(
                f"  score {bucket:<6} trades={b['trades']:<3} "
                f"W={b['wins']:<3} L={b['losses']:<3} "
                f"WR={wr:5.1f}%  pnl={b['pnl']:+.2f}"
            )
    failure = r.failure_breakdown
    if failure:
        lines.append("")
        lines.append("SL failures by mode (Episode 8):")
        for mode, b in failure.items():
            lines.append(
                f"  {mode.value:<20} trades={b['trades']:<3} pnl={b['pnl']:+.2f}"
            )
    return "\n".join(lines)
