"""SMT — Smart Money Technique divergence monitor.

Two correlated markets normally print extremes together. When market A
makes a new high but market B fails to, that's a bearish SMT signal:
hidden weakness in the move. The mirror gives a bullish SMT signal.

This module:
- Holds a small registry of `correlated_pairs` (BTC ↔ ETH by default).
- Computes the most recent N-bar extreme for each symbol on each TF.
- Decides whether the *just-printed* extreme on the lead market is
  matched, exceeded, or missed by the paired market.

The output is used as another confluence component for an existing
CRT signal — *not* as a standalone trade trigger. SMT diverging the
wrong way is one of the three documented failure modes in §P2.9.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crt.models import Direction, Timeframe
from crt.store import CandleStore


# Default correlation map — extend or override at construction time.
DEFAULT_PAIRS: dict[str, str] = {
    "BTC_USDT": "ETH_USDT",
    "ETH_USDT": "BTC_USDT",
    "SOL_USDT": "ETH_USDT",
    "AVAX_USDT": "ETH_USDT",
}


class SMTState(str, Enum):
    BULLISH = "bullish_smt"   # lead made new low, pair did not → look long
    BEARISH = "bearish_smt"   # lead made new high, pair did not → look short
    ALIGNED = "aligned"       # both markets agree, no SMT
    NO_DATA = "no_data"


@dataclass(slots=True)
class SMTReading:
    state: SMTState
    lead_symbol: str
    pair_symbol: str
    lead_extreme: float
    pair_extreme: float
    lookback: int

    @property
    def is_divergent(self) -> bool:
        return self.state in (SMTState.BULLISH, SMTState.BEARISH)


class SMTMonitor:
    """Pairwise divergence checker driven by the candle store."""

    def __init__(
        self,
        store: CandleStore,
        pairs: dict[str, str] | None = None,
        *,
        lookback: int = 20,
    ):
        self.store = store
        self.pairs = pairs or dict(DEFAULT_PAIRS)
        self.lookback = lookback

    def pair_for(self, symbol: str) -> str | None:
        return self.pairs.get(symbol)

    def reading(
        self,
        symbol: str,
        tf: Timeframe,
        direction: Direction,
    ) -> SMTReading:
        pair = self.pair_for(symbol)
        if pair is None:
            return SMTReading(SMTState.NO_DATA, symbol, "", 0.0, 0.0, self.lookback)
        lead = self.store.get(symbol, tf, count=self.lookback)
        other = self.store.get(pair, tf, count=self.lookback)
        if not lead or not other:
            return SMTReading(SMTState.NO_DATA, symbol, pair, 0.0, 0.0, self.lookback)

        if direction is Direction.BEARISH:
            # Bearish SMT: lead just made a new high; pair didn't.
            lead_extreme = max(c.high for c in lead)
            pair_extreme = max(c.high for c in other)
            # The most recent bar made a new extreme if its high equals the
            # rolling max (and is strictly greater than the prior bars).
            recent_made_new = lead[-1].high == lead_extreme and all(
                lead[-1].high > c.high for c in lead[:-1]
            )
            pair_made_new = other[-1].high == pair_extreme and all(
                other[-1].high > c.high for c in other[:-1]
            )
            if recent_made_new and not pair_made_new:
                state = SMTState.BEARISH
            else:
                state = SMTState.ALIGNED
        else:
            lead_extreme = min(c.low for c in lead)
            pair_extreme = min(c.low for c in other)
            recent_made_new = lead[-1].low == lead_extreme and all(
                lead[-1].low < c.low for c in lead[:-1]
            )
            pair_made_new = other[-1].low == pair_extreme and all(
                other[-1].low < c.low for c in other[:-1]
            )
            if recent_made_new and not pair_made_new:
                state = SMTState.BULLISH
            else:
                state = SMTState.ALIGNED

        return SMTReading(
            state=state, lead_symbol=symbol, pair_symbol=pair,
            lead_extreme=lead_extreme, pair_extreme=pair_extreme,
            lookback=self.lookback,
        )
