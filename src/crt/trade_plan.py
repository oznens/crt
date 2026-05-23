"""Trade plan + setup card data structures.

The trade plan turns a Signal + Position into the visual planning
language TradingView's CRT PRO+ indicator uses: a single 1R reference
(entry → stop distance) with TPs expressed as R-multiples. The setup
card is the corner-mounted summary box: model, bias, SMT pair, per-TF
alignment, CISD state, time until current candle closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from crt.context.cisd import CISDStatus
from crt.context.smt import SMTState
from crt.models import Direction, Signal, Timeframe, utc_now


@dataclass(slots=True, frozen=True)
class TradePlan:
    """Risk-multiple framing of a Signal's entry/stop/targets."""

    direction: Direction
    entry: float
    stop: float
    targets: list[float]                # absolute target prices
    r_multiples: list[float] = field(default_factory=list)  # TP distance / 1R

    @property
    def one_r(self) -> float:
        return abs(self.entry - self.stop)

    @classmethod
    def from_signal(cls, sig: Signal) -> "TradePlan":
        """Build a plan from a Signal's existing geometry.

        Entry defaults to range mid + small offset toward DOL; stop is
        just beyond the purge wick. Targets are LHF, initial DOL, and
        an extended DOL (2× from entry past initial DOL).
        """
        if sig.entry_override is not None and sig.stop_override is not None:
            entry, stop = sig.entry_override, sig.stop_override
        else:
            range_size = sig.range_high - sig.range_low
            if sig.direction is Direction.BULLISH:
                entry = sig.range_low + range_size * 0.1
                stop = sig.purge_price - range_size * 0.1
            else:
                entry = sig.range_high - range_size * 0.1
                stop = sig.purge_price + range_size * 0.1

        targets = [sig.lhf, sig.initial_dol]
        if sig.extended_dol is not None:
            targets.append(sig.extended_dol)
        else:
            ext = sig.initial_dol + (sig.initial_dol - sig.lhf)
            targets.append(ext)

        one_r = abs(entry - stop) or 1.0
        r_multiples = [abs(t - entry) / one_r for t in targets]

        return cls(direction=sig.direction, entry=entry, stop=stop,
                   targets=targets, r_multiples=r_multiples)


@dataclass(slots=True)
class SetupCard:
    """The corner-mounted summary used in TradingView-style overlays."""

    symbol: str
    ltf_tf: Timeframe
    htf_tf: Timeframe | None
    model: str                  # "BULL" / "BEAR"
    bias: str                   # "LONG" / "SHORT"
    level: float                # the CRH or CRL the setup is anchored on
    c2_status: str              # "CONF" / "PEND" / "FAIL"
    cisd_status: CISDStatus
    smt_pair: str | None
    smt_state: SMTState | None
    tf_alignment: dict[str, str]    # {"1m": "BEAR-", "15m": "BULL+", ...}
    closes_at: datetime | None      # when the current LTF candle closes
    confluence: float = 0.0

    @property
    def close_in(self) -> timedelta | None:
        if self.closes_at is None:
            return None
        return self.closes_at - utc_now()

    @property
    def close_in_str(self) -> str:
        delta = self.close_in
        if delta is None:
            return "—"
        seconds = max(0, int(delta.total_seconds()))
        h, rem = divmod(seconds, 3600)
        m, _ = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m"
        return f"{m}m"

    def to_table_rows(self) -> list[tuple[str, str]]:
        """Render the card as a flat (label, value) sequence."""
        rows: list[tuple[str, str]] = []
        if self.htf_tf is not None:
            rows.append((f"{self.ltf_tf.value} → {self.htf_tf.value}", "(Auto)"))
        else:
            rows.append((self.ltf_tf.value, "(Auto)"))
        rows.append(("Model", self.model))
        for tf, val in self.tf_alignment.items():
            rows.append((tf, val))
        rows.append(("Level", f"{self.level:.4f}"))
        rows.append(("Mode", "Auto+P2"))
        if self.smt_pair:
            rows.append(("SMT", self.smt_pair))
        rows.append(("Bias", self.bias))
        rows.append(("C2", self.c2_status))
        rows.append(("CISD", self.cisd_status.value.upper()))
        rows.append(("Close", self.close_in_str))
        rows.append(("Confl", f"{self.confluence:+.1f}"))
        return rows
