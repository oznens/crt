"""FastAPI web dashboard endpoints."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from crt.models import CRTSubtype, Direction, Signal, Timeframe, utc_now
from crt.paper import PaperConfig, PaperEngine
from crt.store import CandleStore
from crt.web import WebDashboard, create_app

from tests.conftest import first_ts, make_filler


@pytest.fixture
def dashboard():
    store = CandleStore()
    # Seed with two candles per (symbol, tf) so the watchlist has chg %.
    for sym in ("BTC_USDT", "ETH_USDT"):
        for c in make_filler(sym, Timeframe.H1, first_ts(), 5):
            store.append(c)
    engine = PaperEngine(PaperConfig(starting_balance=10_000.0))
    dash = WebDashboard(
        store, engine,
        watch=[("BTC_USDT", Timeframe.H1), ("ETH_USDT", Timeframe.H1)],
    )
    return dash


def test_state_endpoint_returns_watchlist_and_pnl(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/api/state")
    assert r.status_code == 200
    payload = r.json()
    assert payload["balance"] == 10_000.0
    assert payload["wins"] == 0 and payload["losses"] == 0
    syms = {row["symbol"] for row in payload["watchlist"]}
    assert syms == {"BTC_USDT", "ETH_USDT"}


def test_state_endpoint_surfaces_pushed_signals(dashboard):
    dashboard.push_signal(Signal(
        symbol="BTC_USDT", tf=Timeframe.H1, subtype=CRTSubtype.CLASSIC_3,
        direction=Direction.BULLISH, detected_at=utc_now(),
        range_high=100.0, range_low=90.0, purge_price=89.0,
        confidence=0.8, lhf=95.0, initial_dol=100.0,
        confluence_score=4.5,
    ))
    client = TestClient(create_app(dashboard))
    payload = client.get("/api/state").json()
    assert len(payload["signals"]) == 1
    g = payload["signals"][0]
    assert g["symbol"] == "BTC_USDT"
    assert g["subtype"] == "type_1_classic_3_candle"
    assert g["confluence"] == 4.5


def test_chart_endpoint_returns_plotly_json(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/api/chart", params={"symbol": "BTC_USDT", "tf": "1h"})
    assert r.status_code == 200
    payload = r.json()
    assert "data" in payload and "layout" in payload
    # The first trace is the candlestick.
    assert any(t.get("type") == "candlestick" for t in payload["data"])


def test_chart_endpoint_404_when_no_data(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/api/chart", params={"symbol": "NOTHING_USDT", "tf": "1h"})
    assert r.status_code == 404


def test_chart_endpoint_400_on_unknown_tf(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/api/chart", params={"symbol": "BTC_USDT", "tf": "99q"})
    assert r.status_code == 400


def test_index_serves_html(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "CRT live" in r.text
    assert "Plotly" in r.text  # Plotly script tag should be in the page


def test_healthz(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


def test_index_includes_backtest_panel(dashboard):
    """The HTML page must surface the backtest form so the user can run
    one without leaving the browser."""
    client = TestClient(create_app(dashboard))
    text = client.get("/").text
    assert "Backtest" in text
    assert "runBacktest" in text
    assert "bt-symbols" in text


def test_backtest_endpoint_400_without_symbols(dashboard):
    client = TestClient(create_app(dashboard))
    r = client.post("/api/backtest", json={"tfs": ["1h"]})
    assert r.status_code == 400


def test_index_includes_heatmap_panel(dashboard):
    """The HTML page must expose the heatmap panel + Run button."""
    client = TestClient(create_app(dashboard))
    text = client.get("/").text
    assert "Heatmap" in text
    assert "runHeatmap" in text
    assert "hm-symbols" in text
    assert "heatColor" in text
