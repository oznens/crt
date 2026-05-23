"""Parallel backtest over many symbols.

A single `BacktestRunner` is constrained to one shared `CandleStore`,
which is convenient for correctness but wastes parallelism when scanning
50+ symbols. `parallel_backtest` spawns one mini-runner per symbol —
each owning its own store, detector, paper engine and SMT monitor (with
the correlated pair pre-loaded so SMT readings still resolve) — then
merges the resulting reports.

Concurrency is bounded by a semaphore so we don't hit MEXC's REST
rate-limit when fanning out across the universe.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from crt.backtest.engine import BacktestReport, BacktestRunner
from crt.context import SMTMonitor, Tier
from crt.data.mexc import MexcClient
from crt.models import CRTSubtype, PositionStatus, Timeframe
from crt.paper import FailureMode, PaperConfig

log = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 8


@dataclass(slots=True)
class ParallelBacktestReport:
    """Aggregated report assembled from per-symbol BacktestReports."""

    per_symbol: dict[str, BacktestReport]
    starting_balance: float

    @property
    def ending_balance(self) -> float:
        # The starting balance is replicated per symbol, so accumulate only
        # the deltas (each symbol's realized PnL).
        return self.starting_balance + sum(
            r.ending_balance - r.starting_balance for r in self.per_symbol.values()
        )

    @property
    def total_pnl(self) -> float:
        return self.ending_balance - self.starting_balance

    @property
    def all_signals(self):
        return [s for r in self.per_symbol.values() for s in r.signals]

    @property
    def all_positions(self):
        return [p for r in self.per_symbol.values() for p in r.positions]

    @property
    def wins(self) -> int:
        return sum(1 for p in self.all_positions if p.status == PositionStatus.CLOSED_TP)

    @property
    def losses(self) -> int:
        return sum(1 for p in self.all_positions if p.status == PositionStatus.CLOSED_SL)

    @property
    def win_rate(self) -> float:
        decisive = self.wins + self.losses
        return self.wins / decisive * 100 if decisive else 0.0

    def by_symbol_pnl(self) -> list[tuple[str, float]]:
        """Per-symbol realized PnL, sorted best → worst."""
        rows = [
            (sym, r.ending_balance - r.starting_balance)
            for sym, r in self.per_symbol.items()
        ]
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows

    def by_subtype(self) -> dict[CRTSubtype, dict]:
        out: dict[CRTSubtype, dict] = {}
        for r in self.per_symbol.values():
            for st, b in r.by_subtype().items():
                acc = out.setdefault(
                    st, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
                )
                for k in ("trades", "wins", "losses", "pnl"):
                    acc[k] += b[k]
        return out

    def by_failure_mode(self) -> dict[FailureMode, dict]:
        out: dict[FailureMode, dict] = {}
        for r in self.per_symbol.values():
            for mode, b in r.failure_breakdown.items():
                acc = out.setdefault(mode, {"trades": 0, "pnl": 0.0})
                for k in ("trades", "pnl"):
                    acc[k] += b[k]
        return out


async def parallel_backtest(
    client: MexcClient,
    symbols: list[str],
    timeframes: list[Timeframe],
    *,
    paper_config: PaperConfig | None = None,
    min_tier: Tier = Tier.MEDIUM,
    require_htf_alignment: bool = False,
    min_confluence: float = float("-inf"),
    bars: int = 500,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ParallelBacktestReport:
    """Run a backtest across every (symbol × tf) in parallel.

    Each per-symbol runner gets its own correlated pair pre-loaded so
    SMT readings still resolve. The semaphore caps how many REST calls
    are inflight at once.
    """
    cfg = paper_config or PaperConfig()
    sem = asyncio.Semaphore(concurrency)
    # We need a temporary monitor just to resolve which symbol is paired
    # with which. The monitor itself is stateless w.r.t. the live data.
    pair_for = SMTMonitor.__dict__["pair_for"]
    probe = SMTMonitor(store=None)  # type: ignore[arg-type]

    async def _one(symbol: str) -> tuple[str, BacktestReport]:
        async with sem:
            runner = BacktestRunner(
                symbols=[symbol], timeframes=list(timeframes),
                paper_config=cfg,
                min_tier=min_tier,
                require_htf_alignment=require_htf_alignment,
                min_confluence=min_confluence,
            )
            # Pre-load the correlated pair so SMT readings resolve.
            pair = pair_for(probe, symbol)
            pairs_to_fetch = [symbol] + ([pair] if pair else [])
            for sym in pairs_to_fetch:
                for tf in timeframes:
                    try:
                        candles = await client.fetch_klines(sym, tf, limit=bars)
                        runner.feed(candles)
                    except Exception:
                        log.exception("fetch failed for %s %s", sym, tf.value)
            return symbol, runner.report()

    pairs = await asyncio.gather(*[_one(s) for s in symbols])
    return ParallelBacktestReport(
        per_symbol=dict(pairs),
        starting_balance=cfg.starting_balance,
    )


def format_parallel_report(r: ParallelBacktestReport, top: int = 10) -> str:
    lines: list[str] = []
    lines.append(f"Symbols: {len(r.per_symbol)}")
    lines.append(f"Starting balance: {r.starting_balance:.2f}")
    lines.append(f"Total PnL: {r.total_pnl:+.2f}")
    decisive = r.wins + r.losses
    lines.append(f"Wins: {r.wins}  Losses: {r.losses}  "
                 f"Total decisive: {decisive}  WR: {r.win_rate:.1f}%")

    pnls = r.by_symbol_pnl()
    if pnls:
        lines.append("")
        lines.append(f"Top {min(top, len(pnls))} winners:")
        for sym, pnl in pnls[:top]:
            lines.append(f"  {sym:<14} {pnl:+.2f}")
        if len(pnls) > top:
            lines.append("")
            lines.append(f"Bottom {min(top, len(pnls))} losers:")
            for sym, pnl in pnls[-top:]:
                lines.append(f"  {sym:<14} {pnl:+.2f}")

    sub = r.by_subtype()
    if sub:
        lines.append("")
        lines.append("By subtype (aggregated):")
        for st, b in sub.items():
            decisive = b["wins"] + b["losses"]
            wr = (b["wins"] / decisive * 100) if decisive else 0.0
            lines.append(
                f"  {st.value:<32} trades={b['trades']:<3} "
                f"W={b['wins']:<3} L={b['losses']:<3} "
                f"WR={wr:5.1f}%  pnl={b['pnl']:+.2f}"
            )

    fail = r.by_failure_mode()
    if fail:
        lines.append("")
        lines.append("SL failures by mode (aggregated):")
        for mode, b in fail.items():
            lines.append(f"  {mode.value:<20} trades={b['trades']:<3} pnl={b['pnl']:+.2f}")
    return "\n".join(lines)
