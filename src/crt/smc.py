"""Bridge between our `Candle` ringbuffer and the `smartmoneyconcepts`
library (https://github.com/joshyattridge/smart-money-concepts).

The smc functions consume a pandas DataFrame with lowercase OHLCV columns.
We translate our `Candle` objects into the expected shape, call the
indicator, and return the raw DataFrame so callers can either:
- merge the result back onto candles by aligning the DatetimeIndex, or
- pass it to the plotting layer to draw overlays.

This module deliberately does NOT cache aggressively — recomputation per
candle close is cheap on the rolling window sizes we use (500 bars).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from smartmoneyconcepts import smc

from crt.models import Candle


def candles_to_df(candles: Sequence[Candle]) -> pd.DataFrame:
    """Convert an ordered list of Candle to the smc input shape."""
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        },
        index=pd.DatetimeIndex([c.open_time for c in candles]),
    )


@dataclass(slots=True)
class SMCSnapshot:
    """Bundle of indicator outputs for one (symbol, tf) window."""

    df: pd.DataFrame
    swings: pd.DataFrame
    fvg: pd.DataFrame
    bos_choch: pd.DataFrame
    order_blocks: pd.DataFrame
    liquidity: pd.DataFrame


def compute(candles: Sequence[Candle], *, swing_length: int = 10) -> SMCSnapshot:
    """Run the standard SMC indicator stack against the candle window."""
    df = candles_to_df(candles)
    if df.empty:
        empty = pd.DataFrame()
        return SMCSnapshot(df, empty, empty, empty, empty, empty)
    swings = smc.swing_highs_lows(df, swing_length=swing_length)
    return SMCSnapshot(
        df=df,
        swings=swings,
        fvg=smc.fvg(df),
        bos_choch=smc.bos_choch(df, swings),
        order_blocks=smc.ob(df, swings),
        liquidity=smc.liquidity(df, swings),
    )


def latest_bullish_fvg(snap: SMCSnapshot) -> tuple[float, float] | None:
    """Return (bottom, top) of the most recent unmitigated bullish FVG, or None."""
    if snap.fvg.empty:
        return None
    bullish = snap.fvg[(snap.fvg["FVG"] == 1) & (snap.fvg["MitigatedIndex"].isna())]
    if bullish.empty:
        return None
    last = bullish.iloc[-1]
    return float(last["Bottom"]), float(last["Top"])


def latest_bearish_fvg(snap: SMCSnapshot) -> tuple[float, float] | None:
    if snap.fvg.empty:
        return None
    bearish = snap.fvg[(snap.fvg["FVG"] == -1) & (snap.fvg["MitigatedIndex"].isna())]
    if bearish.empty:
        return None
    last = bearish.iloc[-1]
    return float(last["Bottom"]), float(last["Top"])


def price_in_fvg(snap: SMCSnapshot, price: float) -> int:
    """+1 if price sits inside an unmitigated bullish FVG, -1 inside bearish, 0 otherwise."""
    if snap.fvg.empty:
        return 0
    unmitigated = snap.fvg[snap.fvg["MitigatedIndex"].isna()]
    for _, row in unmitigated.iterrows():
        bottom, top = row["Bottom"], row["Top"]
        if bottom <= price <= top:
            return int(row["FVG"])
    return 0


def recent_bos(snap: SMCSnapshot, lookback: int = 10) -> int | None:
    """Return the direction of the most recent Break of Structure within the
    last `lookback` candles, or None if there isn't one.
    """
    if snap.bos_choch.empty:
        return None
    tail = snap.bos_choch.tail(lookback)
    bos_rows = tail[tail["BOS"].notna() & (tail["BOS"] != 0)]
    if bos_rows.empty:
        return None
    return int(bos_rows.iloc[-1]["BOS"])


def recent_choch(snap: SMCSnapshot, lookback: int = 10) -> int | None:
    """Same for Change of Character (structure-shift inverse)."""
    if snap.bos_choch.empty:
        return None
    tail = snap.bos_choch.tail(lookback)
    choch_rows = tail[tail["CHOCH"].notna() & (tail["CHOCH"] != 0)]
    if choch_rows.empty:
        return None
    return int(choch_rows.iloc[-1]["CHOCH"])
