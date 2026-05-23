"""Replay historical candles through the same detector + paper engine
that the live runtime uses.

Two ways to seed candles:

1. `load_from_mexc(...)` — pull a window of klines via the REST endpoint
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
    Tier,
    candle_tier,
    passes_time_filter,
    signal_aligned_with_htf,
)
from crt.data.mexc import MexcClient
from crt.detector import CRTDetector
from crt.models import (
    Candle,
    CRTSubtype,
    Direction,
    PaperPosition,
    PositionStatus,
    Signal,
    Timeframe,
)
from crt.paper import PaperConfig, PaperEngine
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
    store: CandleStore = field(default_factory=CandleStore)
    engine: PaperEngine = field(init=False)
    detector: CRTDetector = field(init=False)
    signals: list[Signal] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.engine = PaperEngine(self.paper_config)
        self.detector = CRTDetector(self.store)

    # ------------------------------------------------------------------ feed

    def feed(self, candles: Iterable[Candle]) -> None:
        """Replay a stream of candles in chronological order."""
        # Sort defensively in case caller passed an unordered iterable.
        ordered = sorted(candles, key=lambda c: (c.open_time, c.tf.seconds))
        for candle in ordered:
            self._on_candle(candle)

    async def load_from_mexc(
        self,
        client: MexcClient,
        *,
        limit_per_tf: int = 500,
    ) -> None:
        """Bootstrap from MEXC REST: pull the most-recent N closed candles
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
        return BacktestReport(
            symbols=list(self.symbols),
            timeframes=list(self.timeframes),
            starting_balance=self.paper_config.starting_balance,
            ending_balance=self.engine.balance,
            signals=list(self.signals),
            positions=list(self.engine.closed_positions) + list(self.engine.open_positions),
        )

    # ---------------------------------------------------------------- private

    def _on_candle(self, candle: Candle) -> None:
        self.store.append(candle)
        for _closed in self.engine.on_candle(candle):
            pass
        if not passes_time_filter(candle, min_tier=self.min_tier):
            return
        for sig in self.detector.evaluate(candle.symbol, candle.tf):
            if not self._accept_signal(sig):
                continue
            self.signals.append(sig)
            self.engine.on_signal(sig)

    def _accept_signal(self, sig: Signal) -> bool:
        latest = self.store.latest(sig.symbol, sig.tf)
        if latest is None:
            return False
        tier = candle_tier(latest)
        sig.note = f"tier={tier.value}; {sig.note}".strip("; ")
        return signal_aligned_with_htf(
            self.store, sig.symbol, sig.tf, sig.direction,
            require=self.require_htf_alignment,
        )


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
    return "\n".join(lines)
