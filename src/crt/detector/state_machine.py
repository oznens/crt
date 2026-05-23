"""Generic CRT state machine.

Per (symbol, timeframe) we maintain a rolling view of recent candles and try
to fit one of the five subtypes documented in `docs/notes/crt.md` §8a/8b.

Flow:
    1. Look at the most-recent N candles in `store.get(symbol, tf)`.
    2. Pick the candidate range candle (last "beefy" candle larger than a
       rolling median of body sizes).
    3. Check which subtype, if any, is satisfied by the candles that
       follow the range candle.
    4. Emit a Signal when validation passes; otherwise yield nothing.

The detector is intentionally pure (no I/O, no scheduling). The runtime
wires it to the store's "candle closed" events and forwards emitted
signals to the paper engine and TUI.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable

from crt.models import CRTSubtype, Candle, Direction, Signal, Timeframe, utc_now
from crt.store import CandleStore

# How many candles to look back when computing the rolling "beefy" baseline.
BASELINE_WINDOW = 20

# A candle is "beefy" if its body is at least this multiple of the rolling median body.
BEEFY_MULTIPLIER = 1.4

# Maximum number of candles after the range candle to consider for expansion.
MAX_LOOKAHEAD = 8


def _median_body(candles: Iterable[Candle]) -> float:
    bodies = [c.body for c in candles if c.body > 0]
    if not bodies:
        return 0.0
    return float(statistics.median(bodies))


def _is_beefy(candle: Candle, baseline: float) -> bool:
    if baseline <= 0:
        return candle.body > 0
    return candle.body >= BEEFY_MULTIPLIER * baseline


def _wick_purges(candle: Candle, level: float, direction: Direction) -> bool:
    """True if the candle's wick clearly extends beyond `level`.

    For a bullish CRT the purge must dip BELOW range low (the candle's low
    must be < level). For a bearish CRT the purge wicks ABOVE range high.
    """
    if direction is Direction.BULLISH:
        return candle.low < level
    return candle.high > level


def _body_inside(candle: Candle, low: float, high: float) -> bool:
    """Both open and close are within [low, high] — i.e., wick-only break."""
    return low <= candle.open <= high and low <= candle.close <= high


def _build_signal(
    *,
    range_candle: Candle,
    direction: Direction,
    subtype: CRTSubtype,
    purge_price: float,
    confidence: float,
    note: str = "",
) -> Signal:
    crh = range_candle.high
    crl = range_candle.low
    lhf = (crh + crl) / 2.0
    initial_dol = crh if direction is Direction.BULLISH else crl
    return Signal(
        symbol=range_candle.symbol,
        tf=range_candle.tf,
        subtype=subtype,
        direction=direction,
        detected_at=utc_now(),
        range_high=crh,
        range_low=crl,
        purge_price=purge_price,
        confidence=confidence,
        lhf=lhf,
        initial_dol=initial_dol,
        extended_dol=None,
        note=note,
    )


class CRTDetector:
    """Evaluate a (symbol, tf) window for any of the 5 CRT subtypes."""

    def __init__(self, store: CandleStore):
        self.store = store
        # Track which range-candle open_time we've already emitted a signal for,
        # to avoid duplicate signals on the same CRT.
        self._emitted: set[tuple[str, Timeframe, str]] = set()

    def evaluate(self, symbol: str, tf: Timeframe) -> list[Signal]:
        candles = self.store.get(symbol, tf)
        if len(candles) < BASELINE_WINDOW + 3:
            return []

        signals: list[Signal] = []
        # Try each potential range candle from oldest still-relevant to newest-but-one.
        # We need at least 1 candle after it to evaluate a CRT.
        for i in range(len(candles) - 2, len(candles) - MAX_LOOKAHEAD - 1, -1):
            if i < BASELINE_WINDOW:
                break
            range_candle = candles[i]
            baseline_window = candles[max(0, i - BASELINE_WINDOW): i]
            baseline = _median_body(baseline_window)
            if not _is_beefy(range_candle, baseline):
                continue

            following = candles[i + 1:]
            for direction in (Direction.BULLISH, Direction.BEARISH):
                sig = self._classify(range_candle, following, direction)
                if sig is None:
                    continue
                key = (symbol, tf, range_candle.open_time.isoformat())
                if key in self._emitted:
                    continue
                self._emitted.add(key)
                signals.append(sig)
        return signals

    def _classify(
        self,
        range_candle: Candle,
        following: list[Candle],
        direction: Direction,
    ) -> Signal | None:
        if not following:
            return None
        crh = range_candle.high
        crl = range_candle.low

        # Anti-trend filter: bullish CRT expects the range candle to NOT have
        # already closed below its own midpoint when the purge happens, etc.
        # For now we trust the geometric purge filter.

        # ---- Type 2: 2-Candle Aggressive ----
        # The candle immediately after range purges and closes beyond opposite extreme.
        c2 = following[0]
        if _wick_purges(c2, crl if direction is Direction.BULLISH else crh, direction):
            target = crh if direction is Direction.BULLISH else crl
            closed_through = (
                c2.close > target if direction is Direction.BULLISH else c2.close < target
            )
            if closed_through:
                return _build_signal(
                    range_candle=range_candle,
                    direction=direction,
                    subtype=CRTSubtype.AGGRESSIVE_2,
                    purge_price=c2.low if direction is Direction.BULLISH else c2.high,
                    confidence=0.75,
                    note="purge+expansion in single candle",
                )

        # ---- Type 4: Inside Bar ----
        # All bars 2..N stay strictly inside C1's range until one breaks the
        # opposite extreme with a close. The "TS" wick can come from any of the
        # inside bars touching the purge side.
        inside_run: list[Candle] = []
        purge_hit_in_inside = False
        for cand in following[:MAX_LOOKAHEAD]:
            inside = cand.high <= crh and cand.low >= crl
            wicks_purge = _wick_purges(
                cand,
                crl if direction is Direction.BULLISH else crh,
                direction,
            )
            if inside:
                inside_run.append(cand)
                continue
            if wicks_purge and _body_inside(cand, crl, crh):
                # treat as inside in spirit — wick is the engineered TS
                inside_run.append(cand)
                purge_hit_in_inside = True
                continue
            # break candidate — must close past opposite extreme
            target = crh if direction is Direction.BULLISH else crl
            broke = (
                cand.close > target if direction is Direction.BULLISH else cand.close < target
            )
            if broke and len(inside_run) >= 2 and purge_hit_in_inside:
                return _build_signal(
                    range_candle=range_candle,
                    direction=direction,
                    subtype=CRTSubtype.INSIDE_BAR,
                    purge_price=min(c.low for c in inside_run)
                    if direction is Direction.BULLISH
                    else max(c.high for c in inside_run),
                    confidence=0.85,
                    note=f"{len(inside_run)} inside bars then breakout",
                )
            break  # not inside and not the breakout we wanted → stop probing

        # ---- Type 1 / 3 / 5: classic family, requires a clean purge in C2 ----
        if not _wick_purges(c2, crl if direction is Direction.BULLISH else crh, direction):
            return None
        if not _body_inside(c2, crl, crh):
            return None
        purge_price = c2.low if direction is Direction.BULLISH else c2.high

        # Type 1: classic — C3 closes past opposite extreme (preferred over Type 5)
        target = crh if direction is Direction.BULLISH else crl
        if len(following) >= 2:
            c3 = following[1]
            c3_closes_through = (
                c3.close > target if direction is Direction.BULLISH else c3.close < target
            )
            if c3_closes_through:
                return _build_signal(
                    range_candle=range_candle,
                    direction=direction,
                    subtype=CRTSubtype.CLASSIC_3,
                    purge_price=purge_price,
                    confidence=0.8,
                    note="C2 purge, C3 expansion",
                )

        # Type 5: 3rd candle manipulates C2's extreme but does NOT itself close
        # through the opposite extreme — C4 has to do the distribution.
        if len(following) >= 3:
            c3 = following[1]
            c2_extreme = c2.high if direction is Direction.BULLISH else c2.low
            c3_wicks_c2 = (
                c3.high > c2.high if direction is Direction.BULLISH else c3.low < c2.low
            )
            c3_closes_through = (
                c3.close > target if direction is Direction.BULLISH else c3.close < target
            )
            if c3_wicks_c2 and not c3_closes_through:
                c4 = following[2]
                c4_closes_through = (
                    c4.close > target
                    if direction is Direction.BULLISH
                    else c4.close < target
                )
                if c4_closes_through:
                    return _build_signal(
                        range_candle=range_candle,
                        direction=direction,
                        subtype=CRTSubtype.THIRD_CANDLE_REVERSAL,
                        purge_price=c2_extreme,
                        confidence=0.55,
                        note="C3 manipulates C2, C4 distributes",
                    )

        # Type 3: multi-candle expansion — slowly walking to DOL
        broken_at = None
        for j, cand in enumerate(following[1:MAX_LOOKAHEAD], start=2):
            broke = (
                cand.close > target if direction is Direction.BULLISH else cand.close < target
            )
            if broke:
                broken_at = j
                break
        if broken_at is not None and broken_at >= 3:
            return _build_signal(
                range_candle=range_candle,
                direction=direction,
                subtype=CRTSubtype.MULTI_CANDLE,
                purge_price=purge_price,
                confidence=0.45,
                note=f"expansion took {broken_at - 1} candles",
            )
        return None
