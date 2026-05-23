"""Chart rendering smoke test (no network, no browser)."""

from __future__ import annotations

import numpy as np
from datetime import timedelta

from crt.chart import render_chart, write_chart_html
from crt.models import CRTSubtype, Direction, Signal, Timeframe, utc_now

from tests.conftest import first_ts, mk_candle


def _candles(n: int = 80):
    rng = np.random.default_rng(11)
    out = []
    t = first_ts()
    base = 100.0
    for i in range(n):
        o = base + 0.4 * i + rng.normal(0, 0.1)
        c = o + rng.normal(0.2, 0.2)
        h = max(o, c) + abs(rng.normal(0, 0.3))
        low = min(o, c) - abs(rng.normal(0, 0.3))
        out.append(mk_candle("BTC_USDT", Timeframe.H1, t, o, h, low, c))
        t = t + timedelta(hours=1)
    return out


def test_render_chart_produces_figure():
    fig = render_chart(_candles(), [], title="t")
    assert fig is not None
    # Candle trace + at least swing or signal traces
    assert len(fig.data) >= 1
    # Candlestick must be the first trace
    assert fig.data[0].type == "candlestick"


def test_render_chart_with_signals_adds_markers():
    candles = _candles()
    sig = Signal(
        symbol="BTC_USDT", tf=Timeframe.H1,
        subtype=CRTSubtype.CLASSIC_3, direction=Direction.BULLISH,
        detected_at=candles[-3].open_time,
        range_high=candles[-5].high, range_low=candles[-5].low,
        purge_price=candles[-4].low, confidence=0.8,
        lhf=(candles[-5].high + candles[-5].low) / 2,
        initial_dol=candles[-5].high,
    )
    fig = render_chart(candles, [sig])
    types = [getattr(t, "name", "") for t in fig.data]
    assert any("Bullish CRT" in n for n in types)


def test_write_chart_html_drops_file_with_refresh_tag(tmp_path):
    out = tmp_path / "chart.html"
    write_chart_html(_candles(), [], out, title="t", refresh_seconds=30)
    text = out.read_text()
    assert "candlestick" in text.lower()
    assert 'http-equiv="refresh"' in text
    assert 'content="30"' in text


def test_write_chart_html_no_refresh_when_zero(tmp_path):
    out = tmp_path / "chart.html"
    write_chart_html(_candles(), [], out, refresh_seconds=0)
    text = out.read_text()
    assert 'http-equiv="refresh"' not in text
