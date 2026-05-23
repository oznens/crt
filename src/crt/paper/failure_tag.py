"""Post-mortem failure tagging for paper positions that hit their stop.

Per CRT Secrets §P2.9 (Episode 8) there are exactly three reasons a CRT
trade fails:

  SMT_WALL          A correlated market diverged the wrong way — smart
                    money blocked the move.
  COUNTER_TREND     The trade was against the HTF bias / trend.
  EARLY_INVALIDATE  The geometry simply broke before the move could
                    complete — no clear smt or trend reason.

`HALF_DONE` is an extra non-failure tag for trades that hit the 50% LHF
target but didn't continue to the full DOL — those still printed money
even if they closed manually or at break-even, so they shouldn't be
counted as losses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crt.context.smt import SMTMonitor, SMTState
from crt.models import Direction, PaperPosition, PositionStatus
from crt.store import CandleStore


class FailureMode(str, Enum):
    SMT_WALL = "smt_wall"
    COUNTER_TREND = "counter_trend"
    EARLY_INVALIDATE = "early_invalidate"
    HALF_DONE = "half_done"
    NOT_A_FAILURE = "not_a_failure"


@dataclass(slots=True)
class FailureTag:
    mode: FailureMode
    note: str = ""


def classify(
    position: PaperPosition,
    store: CandleStore,
    smt: SMTMonitor | None = None,
) -> FailureTag:
    """Decide which of the three Episode-8 buckets this closed position fits.

    Returns NOT_A_FAILURE when the trade closed at TP — no post-mortem
    needed.
    """
    status = position.status
    if status == PositionStatus.CLOSED_TP:
        return FailureTag(FailureMode.NOT_A_FAILURE, "TP hit")
    if status == PositionStatus.OPEN:
        return FailureTag(FailureMode.NOT_A_FAILURE, "still open")
    if status == PositionStatus.TP1:
        # TP1 (50%) hit but later closed — counts as half-done success.
        return FailureTag(FailureMode.HALF_DONE, "LHF hit before SL")

    sig = position.signal
    # 1) SMT wall — there's an SMT in the OPPOSITE direction of the trade.
    #    e.g. bearish BTC trade failed because BTC just made a new low without
    #    pair confirming → that's a bullish-SMT reading, contradicting the
    #    bearish trade. We probe SMT in the opposite direction to detect it.
    if smt is not None:
        opposite_dir = (Direction.BEARISH if sig.direction is Direction.BULLISH
                        else Direction.BULLISH)
        reading = smt.reading(sig.symbol, sig.tf, opposite_dir)
        want = (SMTState.BEARISH if opposite_dir is Direction.BEARISH
                else SMTState.BULLISH)
        if reading.state is want:
            return FailureTag(FailureMode.SMT_WALL,
                              f"{reading.pair_symbol} diverged the wrong way")

    # 2) Counter-trend — HTF bias disagrees with the trade direction.
    from crt.context.alignment import htf_bias  # local import avoids cycles
    bias = htf_bias(store, sig.symbol, sig.tf)
    if bias is not None and bias is not sig.direction:
        return FailureTag(FailureMode.COUNTER_TREND,
                          f"parent HTF was {bias.value}")

    # 3) Otherwise the geometry just broke before completion.
    return FailureTag(FailureMode.EARLY_INVALIDATE, "no SMT/trend reason")
