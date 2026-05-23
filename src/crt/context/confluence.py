"""Confluence scoring — combine CRT signal geometry with SMC context.

Per the Secrets-Series 4-step recipe (notes §P2.7), a signal is only as
good as the confluences supporting it. This module turns the qualitative
checklist into a numeric score so the runtime can filter weak setups
and the backtest can study which confluences actually edge.

Components considered, with default weights:

    +3   Time-tier HIGH      (NY kill-zone, weekly Mon-Fri, etc.)
    +1   Time-tier MEDIUM
    +0   Time-tier LOW
    +2   HTF bias agrees with the signal direction
    -2   HTF bias disagrees
    +3   Signal triggers inside an unmitigated FVG in the same direction
    -2   Inside an FVG in the *opposite* direction
    +2   Inside an order block aligned with the signal
    -1   Inside an opposing order block
    +2   A BOS in the same direction printed within the last 10 bars
    -1   A BOS in the opposite direction printed within the last 10 bars
    +1   Price recently swept liquidity in the signal's direction

Total ranges roughly -8 .. +13. We expose the breakdown so the TUI / chart
can show *why* a signal scored what it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crt.context.alignment import htf_bias
from crt.context.smt import SMTMonitor, SMTState
from crt.context.time_windows import Tier, candle_tier
from crt.models import Direction, Signal
from crt.smc import SMCSnapshot, price_in_fvg, recent_bos
from crt.store import CandleStore


@dataclass(slots=True)
class ConfluenceScore:
    total: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    def add(self, name: str, value: float) -> None:
        if value == 0:
            return
        self.components[name] = value
        self.total += value

    def summary(self) -> str:
        parts = [f"{k}:{v:+.1f}" for k, v in self.components.items()]
        return f"score={self.total:+.1f}  ({', '.join(parts)})" if parts else f"score={self.total:+.1f}"


# -------------------------------------------------------------------- weights

_TIER_WEIGHT = {Tier.HIGH: 3.0, Tier.MEDIUM: 1.0, Tier.LOW: 0.0, Tier.SKIP: -3.0}


def _ob_alignment(snap: SMCSnapshot, price: float, direction: Direction) -> int:
    """+1 if price is inside an OB aligned with `direction`, -1 if opposing, 0 otherwise."""
    if snap.order_blocks.empty:
        return 0
    obs = snap.order_blocks
    # smc tags bullish OB as +1, bearish as -1; only consider unmitigated.
    unmit = obs[obs["MitigatedIndex"].isna()]
    for _, row in unmit.iterrows():
        if row["Bottom"] <= price <= row["Top"]:
            ob_dir = int(row["OB"])
            sig_dir = 1 if direction is Direction.BULLISH else -1
            return 1 if ob_dir == sig_dir else -1
    return 0


def _recent_liquidity_sweep(snap: SMCSnapshot, direction: Direction, lookback: int = 10) -> int:
    """+1 if a liquidity sweep matching the direction printed recently."""
    if snap.liquidity.empty:
        return 0
    tail = snap.liquidity.tail(lookback)
    swept = tail[tail["Swept"].notna() & (tail["Liquidity"] != 0)]
    if swept.empty:
        return 0
    last = swept.iloc[-1]
    # Bullish CRT wants SSL (downside liquidity = -1) to have been swept.
    want = -1 if direction is Direction.BULLISH else 1
    return 1 if int(last["Liquidity"]) == want else 0


# ------------------------------------------------------------------- public api


def score_signal(
    signal: Signal,
    store: CandleStore,
    snap: SMCSnapshot,
    smt: SMTMonitor | None = None,
) -> ConfluenceScore:
    """Compute the confluence score for an emitted signal.

    `snap` is the SMC indicator stack computed on the same (symbol, tf)
    window the signal was detected on.
    """
    out = ConfluenceScore()

    # Time tier — measured on the candle that triggered the signal.
    latest = store.latest(signal.symbol, signal.tf)
    if latest is not None:
        tier = candle_tier(latest)
        out.add(f"tier_{tier.value}", _TIER_WEIGHT[tier])

    # HTF alignment
    bias = htf_bias(store, signal.symbol, signal.tf)
    if bias is signal.direction:
        out.add("htf_agree", 2.0)
    elif bias is not None and bias is not signal.direction:
        out.add("htf_disagree", -2.0)

    # FVG containment — the signal's "purge price" is the most extreme
    # point of the manipulation, often where a same-direction FVG would sit.
    fvg_dir = price_in_fvg(snap, signal.purge_price)
    sig_dir = 1 if signal.direction is Direction.BULLISH else -1
    if fvg_dir == sig_dir:
        out.add("fvg_aligned", 3.0)
    elif fvg_dir == -sig_dir:
        out.add("fvg_opposing", -2.0)

    # Order-block containment
    ob = _ob_alignment(snap, signal.purge_price, signal.direction)
    if ob > 0:
        out.add("ob_aligned", 2.0)
    elif ob < 0:
        out.add("ob_opposing", -1.0)

    # Recent BOS
    bos_dir = recent_bos(snap, lookback=10)
    if bos_dir == sig_dir:
        out.add("bos_aligned", 2.0)
    elif bos_dir == -sig_dir:
        out.add("bos_opposing", -1.0)

    # Liquidity sweep
    if _recent_liquidity_sweep(snap, signal.direction):
        out.add("liquidity_swept", 1.0)

    # SMT — correlated pair divergence
    if smt is not None:
        reading = smt.reading(signal.symbol, signal.tf, signal.direction)
        want = (SMTState.BULLISH if signal.direction is Direction.BULLISH
                else SMTState.BEARISH)
        opposite = (SMTState.BEARISH if signal.direction is Direction.BULLISH
                    else SMTState.BULLISH)
        if reading.state is want:
            out.add("smt_aligned", 2.0)
        elif reading.state is opposite:
            out.add("smt_opposing", -3.0)

    return out
