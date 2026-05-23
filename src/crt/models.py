"""Core dataclasses shared across data, detector, signal and paper layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

    @property
    def seconds(self) -> int:
        return {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
        }[self.value]


# HTF → LTF execution mapping from CRT doctrine (notes §2).
HTF_TO_LTF: dict[Timeframe, Timeframe] = {
    Timeframe.D1: Timeframe.M15,
    Timeframe.H4: Timeframe.M5,
    Timeframe.W1: Timeframe.H1,
    # Monthly → H4 not modeled yet (no monthly stream in MVP).
}


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    tf: Timeframe
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool = True

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0


class CRTSubtype(str, Enum):
    CLASSIC_3 = "type_1_classic_3_candle"
    AGGRESSIVE_2 = "type_2_aggressive_2_candle"
    MULTI_CANDLE = "type_3_multi_candle"
    INSIDE_BAR = "type_4_inside_bar"
    THIRD_CANDLE_REVERSAL = "type_5_third_candle_reversal"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(slots=True)
class Signal:
    """A confirmed CRT setup with projected DOL ladder."""

    symbol: str
    tf: Timeframe
    subtype: CRTSubtype
    direction: Direction
    detected_at: datetime
    range_high: float  # CRH
    range_low: float   # CRL
    purge_price: float  # extreme of the purge wick beyond CRH/CRL
    confidence: float   # 0..1, the detector's geometric confidence
    lhf: float          # Low Hanging Fruit = 50% of range candle
    initial_dol: float  # opposite extreme (CRH for bullish, CRL for bearish)
    extended_dol: float | None = None  # next external SSL/BSL if known
    note: str = ""
    # Confluence score attached after detection. Lazily filled by the
    # runtime / backtest from crt.context.confluence.score_signal.
    confluence_score: float = 0.0
    confluence_breakdown: dict = field(default_factory=dict)


class PositionStatus(str, Enum):
    OPEN = "open"
    TP1 = "tp1_hit"
    TP2 = "tp2_hit"
    CLOSED_TP = "closed_tp"
    CLOSED_SL = "closed_sl"
    CLOSED_MANUAL = "closed_manual"


@dataclass(slots=True)
class PaperPosition:
    signal: Signal
    entry_price: float
    stop_loss: float
    take_profits: list[float]  # [LHF, Initial DOL, Extended DOL]
    size: float
    opened_at: datetime
    status: PositionStatus = PositionStatus.OPEN
    closed_at: datetime | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def side(self) -> Direction:
        return self.signal.direction


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
