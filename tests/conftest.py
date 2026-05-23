"""Shared fixtures + helpers for building synthetic candles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.models import Candle, Timeframe


def mk_candle(
    symbol: str,
    tf: Timeframe,
    t: datetime,
    o: float,
    h: float,
    low: float,
    c: float,
    v: float = 1.0,
) -> Candle:
    return Candle(
        symbol=symbol, tf=tf, open_time=t,
        open=o, high=h, low=low, close=c, volume=v, closed=True,
    )


def make_filler(
    symbol: str,
    tf: Timeframe,
    start: datetime,
    count: int,
    *,
    base: float = 100.0,
    body: float = 0.3,
) -> list[Candle]:
    """Build a flat baseline of small-body candles around `base`."""
    out: list[Candle] = []
    t = start
    direction = 1
    px = base
    for _i in range(count):
        o = px
        c = px + direction * body
        h = max(o, c) + body * 0.2
        low = min(o, c) - body * 0.2
        out.append(mk_candle(symbol, tf, t, o, h, low, c))
        px = c
        direction *= -1
        t = t + timedelta(seconds=tf.seconds)
    return out


def first_ts() -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc)
