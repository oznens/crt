"""HTF → LTF alignment helpers.

A CRT setup on the LTF only matters if the HTF candle it belongs to has
the same directional bias. Per the deck (§2):

    Monthly → H4 PO3
    Weekly  → H1 PO3
    Daily   → M15 PO3
    4H      → M5 PO3

The simplest practical alignment: the HTF candle currently in progress
must agree with the LTF setup's direction.
"""

from __future__ import annotations

from crt.models import Candle, Direction, Timeframe
from crt.store import CandleStore

LTF_TO_HTF: dict[Timeframe, Timeframe] = {
    Timeframe.M5: Timeframe.H4,
    Timeframe.M15: Timeframe.D1,
    Timeframe.H1: Timeframe.W1,
    Timeframe.H4: Timeframe.W1,   # also Monthly when we add it
}


def parent_tf(ltf: Timeframe) -> Timeframe | None:
    return LTF_TO_HTF.get(ltf)


def htf_bias(store: CandleStore, symbol: str, ltf: Timeframe) -> Direction | None:
    """Return the dominant direction of the parent HTF candle in progress.

    None when we don't yet have HTF data or the parent TF isn't configured.
    """
    htf = parent_tf(ltf)
    if htf is None:
        return None
    htf_candles = store.get(symbol, htf)
    if not htf_candles:
        return None
    htf_current = htf_candles[-1]
    # Use the current HTF candle's body direction as the simplest bias signal.
    return Direction.BULLISH if htf_current.is_bullish else Direction.BEARISH


def signal_aligned_with_htf(
    store: CandleStore,
    symbol: str,
    ltf: Timeframe,
    direction: Direction,
    *,
    require: bool = False,
) -> bool:
    """Return True if the signal's direction agrees with the parent HTF bias.

    `require=False` (default) returns True when HTF data is missing so the
    detector doesn't drop signals during startup. Set to True for strict mode.
    """
    bias = htf_bias(store, symbol, ltf)
    if bias is None:
        return not require
    return bias is direction


def latest_htf_candle(
    store: CandleStore, symbol: str, ltf: Timeframe,
) -> Candle | None:
    htf = parent_tf(ltf)
    if htf is None:
        return None
    candles = store.get(symbol, htf)
    return candles[-1] if candles else None
