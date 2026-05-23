"""Per-(symbol, timeframe) ringbuffer of closed candles."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from crt.models import Candle, Timeframe


class CandleStore:
    """Bounded ringbuffer keyed by (symbol, timeframe)."""

    def __init__(self, maxlen: int = 500):
        self._maxlen = maxlen
        self._buf: dict[tuple[str, Timeframe], deque[Candle]] = {}

    def append(self, candle: Candle) -> None:
        key = (candle.symbol, candle.tf)
        buf = self._buf.get(key)
        if buf is None:
            buf = deque(maxlen=self._maxlen)
            self._buf[key] = buf
        # Deduplicate by open_time — replays would otherwise create phantom candles.
        if buf and buf[-1].open_time == candle.open_time:
            buf[-1] = candle
            return
        buf.append(candle)

    def get(self, symbol: str, tf: Timeframe, count: int | None = None) -> list[Candle]:
        buf = self._buf.get((symbol, tf))
        if buf is None:
            return []
        if count is None or count >= len(buf):
            return list(buf)
        return list(buf)[-count:]

    def latest(self, symbol: str, tf: Timeframe) -> Candle | None:
        buf = self._buf.get((symbol, tf))
        return buf[-1] if buf else None

    def symbols(self) -> Iterable[str]:
        return {k[0] for k in self._buf}

    def has(self, symbol: str, tf: Timeframe) -> bool:
        return (symbol, tf) in self._buf
