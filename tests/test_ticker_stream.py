"""Pure-function tests for the Bybit ticker stream parser + on_tick."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from crt.data.bybit_ws import (
    build_ticker_subscribe_messages,
    parse_ticker_push,
)
from crt.models import CRTSubtype, Direction, PositionStatus, Signal, Timeframe
from crt.paper import PaperEngine
from crt.paper.engine import PaperConfig


def test_parse_ticker_push_last_price():
    msg = {
        "topic": "tickers.BTCUSDT",
        "type": "snapshot",
        "data": {"symbol": "BTCUSDT", "lastPrice": "67100.5",
                 "markPrice": "67099.0"},
    }
    out = parse_ticker_push(msg)
    assert out is not None
    sym, price = out
    assert sym == "BTC_USDT"
    assert price == 67100.5


def test_parse_ticker_falls_back_to_mark_price():
    msg = {
        "topic": "tickers.ETHUSDT",
        "data": {"symbol": "ETHUSDT", "markPrice": "3500.25"},
    }
    out = parse_ticker_push(msg)
    assert out == ("ETH_USDT", 3500.25)


def test_parse_ticker_ignores_non_ticker_topics():
    assert parse_ticker_push({"topic": "kline.15.BTCUSDT"}) is None
    assert parse_ticker_push({"op": "subscribe"}) is None


def test_build_ticker_subscribe_messages_batches_at_ten():
    msgs = build_ticker_subscribe_messages([f"S{i}_USDT" for i in range(12)])
    assert len(msgs) == 2
    a = json.loads(msgs[0])
    b = json.loads(msgs[1])
    assert a["op"] == "subscribe"
    assert len(a["args"]) == 10
    assert len(b["args"]) == 2
    assert a["args"][0].startswith("tickers.")


def _bullish_signal() -> Signal:
    return Signal(
        symbol="BTC_USDT", tf=Timeframe.H1,
        subtype=CRTSubtype.CLASSIC_3, direction=Direction.BULLISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0, purge_price=89.0,
        confidence=0.8, lhf=95.0, initial_dol=100.0,
    )


def test_on_tick_fills_pending_when_price_touches_entry():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pending = engine.on_signal(_bullish_signal())
    # Entry ≈ 91.0. A live tick that crosses it should fill.
    engine.on_tick("BTC_USDT", 91.0)
    assert pending.status is PositionStatus.OPEN
    assert pending in engine.open_positions


def test_on_tick_cancels_pending_when_stop_hits_first():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pending = engine.on_signal(_bullish_signal())
    # Stop ≈ 88.0. A tick below should cancel before any fill.
    engine.on_tick("BTC_USDT", 85.0)
    assert pending.status is PositionStatus.PENDING_CANCELLED
    assert pending in engine.closed_positions
    assert engine.pending_orders == []


def test_on_tick_closes_open_position_on_stop():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pending = engine.on_signal(_bullish_signal())
    # Fill it first.
    engine.on_tick("BTC_USDT", 91.0)
    assert pending.status is PositionStatus.OPEN
    # Now a tick at the stop blows it.
    engine.on_tick("BTC_USDT", 87.5)
    assert pending.status is PositionStatus.CLOSED_SL
    assert pending.realized_pnl < 0


def test_on_tick_closes_open_position_on_tp2():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pending = engine.on_signal(_bullish_signal())
    engine.on_tick("BTC_USDT", 91.0)  # fill
    engine.on_tick("BTC_USDT", 100.5)  # past TP2 (100)
    assert pending.status is PositionStatus.CLOSED_TP
    assert pending.realized_pnl > 0


def test_on_tick_refreshes_unrealized_pnl():
    engine = PaperEngine(PaperConfig(risk_per_trade=100.0))
    pending = engine.on_signal(_bullish_signal())
    engine.on_tick("BTC_USDT", 91.0)  # fill at entry
    engine.on_tick("BTC_USDT", 93.0)  # tick above entry
    assert pending.unrealized_pnl > 0
