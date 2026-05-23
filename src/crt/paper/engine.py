"""Paper trading engine driven by detector signals.

Risk model (MVP):
- Entry: at the purge candle close (next bar open in practice — we use signal.detection price).
- Stop loss: just beyond the purge wick (buffer = ATR-ish proxy = 0.1× range).
- Take profits: ladder = [LHF, Initial DOL, Extended DOL or 2× range projection].
- Position size: fixed `risk_per_trade` USD divided by (entry - stop).

Position lifecycle:
- OPEN → TP1 → TP2 → CLOSED_TP (or CLOSED_SL).
- We mark-to-market on every candle close for the position's symbol+TF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from crt.models import Candle, Direction, PaperPosition, PositionStatus, Signal, utc_now

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PaperConfig:
    starting_balance: float = 10_000.0
    risk_per_trade: float = 100.0  # USD risked per signal
    sl_buffer_pct: float = 0.1     # extra cushion beyond purge wick, as % of range


@dataclass(slots=True)
class PaperEngine:
    config: PaperConfig = field(default_factory=PaperConfig)
    balance: float = field(init=False)
    open_positions: list[PaperPosition] = field(default_factory=list)
    closed_positions: list[PaperPosition] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.balance = self.config.starting_balance

    # ------------------------------------------------------------------ public

    def on_signal(
        self,
        signal: Signal,
        fill_candle: Candle | None = None,
    ) -> PaperPosition | None:
        """Open a paper position from a confirmed signal.

        `fill_candle` is the candle that emitted the signal — its
        open_time becomes the position's `opened_at` so backtest/replay
        positions get historically-correct timestamps (otherwise we'd
        stamp every position with "now"). The full pending-order /
        limit-fill model is a follow-up; right now we still open
        optimistically at the computed entry.
        """
        if any(p.signal is signal for p in self.open_positions):
            return None
        entry, stop = self._entry_and_stop(signal)
        if entry == stop:
            return None
        risk_per_unit = abs(entry - stop)
        size = self.config.risk_per_trade / risk_per_unit
        tps = self._take_profits(signal)
        pos = PaperPosition(
            signal=signal,
            entry_price=entry,
            stop_loss=stop,
            take_profits=tps,
            size=size,
            opened_at=utc_now() if fill_candle is None else fill_candle.open_time,
        )
        self.open_positions.append(pos)
        log.info(
            "PAPER OPEN %s %s %s entry=%.6f sl=%.6f tps=%s size=%.4f",
            signal.symbol, signal.tf.value, signal.direction.value,
            entry, stop, tps, size,
        )
        return pos

    def on_candle(self, candle: Candle) -> list[PaperPosition]:
        """Update PnL and check exits for any positions on this symbol/tf."""
        closed_this_tick: list[PaperPosition] = []
        for pos in list(self.open_positions):
            if pos.signal.symbol != candle.symbol or pos.signal.tf != candle.tf:
                continue
            self._mark_to_market(pos, candle)
            if pos.status in (PositionStatus.CLOSED_TP, PositionStatus.CLOSED_SL):
                self.open_positions.remove(pos)
                self.closed_positions.append(pos)
                closed_this_tick.append(pos)
        return closed_this_tick

    # ----------------------------------------------------------------- helpers

    def _entry_and_stop(self, sig: Signal) -> tuple[float, float]:
        # Detectors with explicit geometry (e.g. Model #1) can override entry
        # and stop directly; otherwise we use the classic CRT retrace logic.
        if sig.entry_override is not None and sig.stop_override is not None:
            return sig.entry_override, sig.stop_override
        range_size = sig.range_high - sig.range_low
        buffer = range_size * self.config.sl_buffer_pct
        if sig.direction is Direction.BULLISH:
            entry = sig.range_low + range_size * 0.1
            stop = sig.purge_price - buffer
        else:
            entry = sig.range_high - range_size * 0.1
            stop = sig.purge_price + buffer
        return entry, stop

    def _take_profits(self, sig: Signal) -> list[float]:
        # CRT doctrine: exactly two targets — LHF (50%) and Initial DOL.
        return [sig.lhf, sig.initial_dol]

    def _mark_to_market(self, pos: PaperPosition, c: Candle) -> None:
        # Stop hit?
        if pos.side is Direction.BULLISH and c.low <= pos.stop_loss:
            self._close(pos, pos.stop_loss, PositionStatus.CLOSED_SL, c)
            return
        if pos.side is Direction.BEARISH and c.high >= pos.stop_loss:
            self._close(pos, pos.stop_loss, PositionStatus.CLOSED_SL, c)
            return
        # TP ladder. CRT doctrine: when TP1 (LHF) is touched, move the
        # stop to break-even so the remainder runs risk-free toward TP2.
        tp1, tp2 = pos.take_profits[0], pos.take_profits[1]
        if pos.side is Direction.BULLISH:
            if c.high >= tp2 and pos.status != PositionStatus.CLOSED_TP:
                self._close(pos, tp2, PositionStatus.CLOSED_TP, c)
                return
            if c.high >= tp1 and pos.status == PositionStatus.OPEN:
                pos.status = PositionStatus.TP1
                old_stop = pos.stop_loss
                if pos.stop_loss < pos.entry_price:
                    pos.stop_loss = pos.entry_price  # break-even
                pos.notes.append(
                    f"TP1 hit @ {tp1:.6f} — stop {old_stop:.6f} → "
                    f"{pos.stop_loss:.6f} (break-even)"
                )
        else:
            if c.low <= tp2 and pos.status != PositionStatus.CLOSED_TP:
                self._close(pos, tp2, PositionStatus.CLOSED_TP, c)
                return
            if c.low <= tp1 and pos.status == PositionStatus.OPEN:
                pos.status = PositionStatus.TP1
                old_stop = pos.stop_loss
                if pos.stop_loss > pos.entry_price:
                    pos.stop_loss = pos.entry_price
                pos.notes.append(
                    f"TP1 hit @ {tp1:.6f} — stop {old_stop:.6f} → "
                    f"{pos.stop_loss:.6f} (break-even)"
                )
        # Unrealized PnL
        pnl = (c.close - pos.entry_price) * pos.size
        if pos.side is Direction.BEARISH:
            pnl = -pnl
        pos.unrealized_pnl = pnl

    def _close(self, pos: PaperPosition, price: float, status: PositionStatus, c: Candle) -> None:
        pnl = (price - pos.entry_price) * pos.size
        if pos.side is Direction.BEARISH:
            pnl = -pnl
        pos.realized_pnl = pnl
        pos.unrealized_pnl = 0.0
        pos.status = status
        pos.closed_at = c.open_time
        self.balance += pnl
        log.info(
            "PAPER CLOSE %s %s %s @ %.6f pnl=%.2f balance=%.2f",
            pos.signal.symbol, pos.signal.tf.value, status.value,
            price, pnl, self.balance,
        )
