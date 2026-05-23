"""CISD detection + TradePlan + SetupCard surface."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crt.context import CISDStatus, evaluate_cisd
from crt.context.smt import SMTState
from crt.models import CRTSubtype, Direction, Signal, Timeframe
from crt.trade_plan import SetupCard, TradePlan

from tests.conftest import mk_candle

TF = Timeframe.H1
SYM = "BTC_USDT"


def _bullish_signal() -> Signal:
    return Signal(
        symbol=SYM, tf=TF, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BULLISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0, purge_price=89.0,
        confidence=0.8, lhf=95.0, initial_dol=100.0,
    )


def _bearish_signal() -> Signal:
    return Signal(
        symbol=SYM, tf=TF, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BEARISH,
        detected_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        range_high=100.0, range_low=90.0, purge_price=101.0,
        confidence=0.8, lhf=95.0, initial_dol=90.0,
    )


def _series(direction: str, prices: list[tuple[float, float, float, float]]):
    t = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    out = []
    for i, (o, h, low, c) in enumerate(prices):
        out.append(mk_candle(SYM, TF, t + timedelta(hours=i), o, h, low, c))
    return out


def test_bullish_cisd_active_when_close_above_swept_low():
    sig = _bullish_signal()  # swept low at 89
    post = _series("bull", [
        (89.5, 90.5, 89.0, 90.2),  # body closes above 89 → CISD ACTIVE
    ])
    r = evaluate_cisd(sig, post)
    assert r.status is CISDStatus.ACTIVE
    assert r.confirm_candle is post[0]


def test_bullish_cisd_invalidated_when_price_drives_lower():
    sig = _bullish_signal()  # swept low at 89
    post = _series("bull", [
        (88.5, 88.9, 87.0, 87.3),  # closes well below the sweep
    ])
    r = evaluate_cisd(sig, post)
    assert r.status is CISDStatus.INVALIDATED


def test_bearish_cisd_active_when_close_below_swept_high():
    sig = _bearish_signal()  # swept high at 101
    post = _series("bear", [
        (100.7, 101.2, 99.5, 99.9),  # close below 101 → ACTIVE
    ])
    r = evaluate_cisd(sig, post)
    assert r.status is CISDStatus.ACTIVE


def test_cisd_pending_when_window_empty():
    r = evaluate_cisd(_bullish_signal(), [])
    assert r.status is CISDStatus.PENDING


def test_trade_plan_from_signal_produces_targets_and_r_multiples():
    plan = TradePlan.from_signal(_bullish_signal())
    assert plan.direction is Direction.BULLISH
    assert plan.entry < plan.targets[-1]
    assert plan.stop < plan.entry
    assert len(plan.targets) == 3
    assert len(plan.r_multiples) == 3
    # All R multiples positive
    assert all(r > 0 for r in plan.r_multiples)


def test_trade_plan_honors_overrides_when_present():
    sig = _bullish_signal()
    sig.entry_override = 92.5
    sig.stop_override = 88.0
    plan = TradePlan.from_signal(sig)
    assert plan.entry == 92.5
    assert plan.stop == 88.0


def test_setup_card_to_table_rows_includes_key_fields():
    card = SetupCard(
        symbol=SYM, ltf_tf=TF, htf_tf=Timeframe.D1,
        model="BEAR", bias="SHORT", level=655.7,
        c2_status="CONF", cisd_status=CISDStatus.ACTIVE,
        smt_pair="BTC_USDT+ETH_USDT", smt_state=SMTState.BEARISH,
        tf_alignment={"1m": "BEAR-", "15m": "BULL+", "4h": "BULL+", "1h": "BEAR-"},
        closes_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        confluence=4.5,
    )
    rows = card.to_table_rows()
    labels = {label for label, _ in rows}
    assert "Model" in labels
    assert "Bias" in labels
    assert "C2" in labels
    assert "CISD" in labels
    assert "SMT" in labels
    # CISD value is uppercased
    assert any(label == "CISD" and val == "ACTIVE" for label, val in rows)
