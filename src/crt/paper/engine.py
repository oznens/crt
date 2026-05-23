"""Paper trading engine driven by detector signals.

Order lifecycle:

    on_signal(sig, fill_candle) → PENDING in `pending_orders`
       |
       v   (subsequent candles via on_candle)
    PENDING --fill→ OPEN in `open_positions`
           --cancelled→ CLOSED in `closed_positions` (PENDING_CANCELLED)
           --expired→  CLOSED in `closed_positions` (PENDING_EXPIRED)

    OPEN --TP1 touched→ TP1 (stop trailed to break-even, still in open_positions)
         --TP2 reached→ CLOSED_TP
         --SL hit    → CLOSED_SL

Mark-to-market runs on every closed candle. CRT doctrine: entry is a
limit waiting for retracement into the range, not a market order. A
pending order is cancelled if price reaches the stop without ever
filling the entry; it expires if the entry isn't reached within
`PENDING_LIFETIME_CANDLES`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from crt.models import Candle, Direction, PaperPosition, PositionStatus, Signal, utc_now

log = logging.getLogger(__name__)


# How many candles a parked limit order is allowed to live before
# auto-cancelling. Per CRT doctrine, if entry isn't reached within a
# handful of candles the setup is stale and a fresh signal should be
# waited for instead.
PENDING_LIFETIME_CANDLES = 5


@dataclass(slots=True)
class PaperConfig:
    starting_balance: float = 10_000.0
    risk_per_trade: float = 100.0  # USD risked per signal
    sl_buffer_pct: float = 0.1     # extra cushion beyond purge wick, as % of range


@dataclass(slots=True)
class PaperEngine:
    config: PaperConfig = field(default_factory=PaperConfig)
    balance: float = field(init=False)
    pending_orders: list[PaperPosition] = field(default_factory=list)
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
        """Park a PENDING limit order from a confirmed signal.

        `fill_candle` is the candle that emitted the signal — its
        open_time stamps `opened_at`. The order stays pending until a
        later candle's [low, high] crosses the entry (FILL), crosses
        the stop first (CANCELLED), or PENDING_LIFETIME_CANDLES pass
        (EXPIRED).
        """
        if any(p.signal is signal for p in self.pending_orders
               + self.open_positions):
            return None
        entry, stop = self._entry_and_stop(signal)
        if entry == stop:
            return None
        risk_per_unit = abs(entry - stop)
        size = self.config.risk_per_trade / risk_per_unit
        tps = self._take_profits(signal)
        # Prefer the signal's detected_at so a synthetic test sequence
        # in 2024 doesn't end up with opened_at = real-time-now (which
        # would break age-based lifetime expiry).
        if fill_candle is not None:
            opened_at = fill_candle.open_time
        else:
            opened_at = signal.detected_at or utc_now()
        pending = PaperPosition(
            signal=signal,
            entry_price=entry,
            stop_loss=stop,
            take_profits=tps,
            size=size,
            opened_at=opened_at,
            status=PositionStatus.PENDING,
        )
        self.pending_orders.append(pending)
        log.info(
            "PAPER PENDING %s %s %s entry=%.6f sl=%.6f tps=%s size=%.4f",
            signal.symbol, signal.tf.value, signal.direction.value,
            entry, stop, tps, size,
        )
        return pending

    def on_candle(self, candle: Candle) -> list[PaperPosition]:
        """Process pending orders + filled positions for this symbol/tf.

        Returns the list of positions that transitioned to a *terminal*
        state on this tick (CLOSED_TP / CLOSED_SL / PENDING_CANCELLED /
        PENDING_EXPIRED).
        """
        ended: list[PaperPosition] = []

        # 1) Pending orders — try to fill, cancel, or expire.
        for pending in list(self.pending_orders):
            if (pending.signal.symbol != candle.symbol
                    or pending.signal.tf != candle.tf):
                continue
            result = self._process_pending(pending, candle)
            if result == "filled":
                self.pending_orders.remove(pending)
                self.open_positions.append(pending)
            elif result in ("cancelled", "expired"):
                self.pending_orders.remove(pending)
                self.closed_positions.append(pending)
                ended.append(pending)

        # 2) Filled positions — mark-to-market.
        for pos in list(self.open_positions):
            if pos.signal.symbol != candle.symbol or pos.signal.tf != candle.tf:
                continue
            self._mark_to_market(pos, candle)
            if pos.status in (PositionStatus.CLOSED_TP, PositionStatus.CLOSED_SL):
                self.open_positions.remove(pos)
                self.closed_positions.append(pos)
                ended.append(pos)

        return ended

    # ----------------------------------------------------------------- helpers

    def _entry_and_stop(self, sig: Signal) -> tuple[float, float]:
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

    def _process_pending(self, pending: PaperPosition, c: Candle) -> str:
        """Resolve a parked limit order against the current candle.

        Returns one of: "filled" | "cancelled" | "expired" | "still_pending".
        """
        bull = pending.side is Direction.BULLISH
        entry = pending.entry_price
        stop = pending.stop_loss

        # Stop hit first → cancel before any fill is possible.
        if bull and c.low <= stop:
            pending.status = PositionStatus.PENDING_CANCELLED
            pending.closed_at = c.open_time
            pending.notes.append(
                f"PENDING cancelled — candle low {c.low:.6f} reached "
                f"stop {stop:.6f} before fill"
            )
            return "cancelled"
        if not bull and c.high >= stop:
            pending.status = PositionStatus.PENDING_CANCELLED
            pending.closed_at = c.open_time
            pending.notes.append(
                f"PENDING cancelled — candle high {c.high:.6f} reached "
                f"stop {stop:.6f} before fill"
            )
            return "cancelled"

        # Entry reached this candle → fill at the limit price.
        if c.low <= entry <= c.high:
            pending.status = PositionStatus.OPEN
            pending.filled_at = c.open_time
            pending.notes.append(f"FILLED @ {entry:.6f}")
            return "filled"

        # Lifetime expiry.
        candle_seconds = pending.signal.tf.seconds
        age = (c.open_time - pending.opened_at).total_seconds() / candle_seconds
        if age >= PENDING_LIFETIME_CANDLES:
            pending.status = PositionStatus.PENDING_EXPIRED
            pending.closed_at = c.open_time
            pending.notes.append(
                f"PENDING expired after {int(age)} candles without fill"
            )
            return "expired"
        return "still_pending"

    def _mark_to_market(self, pos: PaperPosition, c: Candle) -> None:
        # Stop hit?
        if pos.side is Direction.BULLISH and c.low <= pos.stop_loss:
            self._close(pos, pos.stop_loss, PositionStatus.CLOSED_SL, c)
            return
        if pos.side is Direction.BEARISH and c.high >= pos.stop_loss:
            self._close(pos, pos.stop_loss, PositionStatus.CLOSED_SL, c)
            return
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
