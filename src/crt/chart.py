"""Plotly-based candle chart with SMC overlays and CRT signal markers.

Outputs a self-contained HTML file that can be opened in any browser.
For live updates the runtime re-renders the file every N candles; the
HTML embeds a `<meta http-equiv="refresh">` so the browser reloads
automatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from crt.models import Candle, Direction, Signal
from crt.smc import SMCSnapshot, compute


def _shapes_for_fvgs(snap: SMCSnapshot, df_index) -> list[dict]:
    """smc returns rows indexed 0..N-1; positional alignment to df_index."""
    import pandas as pd
    shapes: list[dict] = []
    if snap.fvg.empty:
        return shapes
    last_ts = df_index[-1]
    for pos, row in enumerate(snap.fvg.itertuples(index=False)):
        if row.FVG not in (1, -1):
            continue
        if pos >= len(df_index):
            continue
        start = df_index[pos]
        mit_idx = row.MitigatedIndex
        if pd.notna(mit_idx):
            mit_idx = int(mit_idx)
            end = df_index[mit_idx] if mit_idx < len(df_index) else last_ts
        else:
            end = last_ts
        color = "rgba(34, 139, 34, 0.18)" if row.FVG == 1 else "rgba(220, 20, 60, 0.18)"
        shapes.append(dict(
            type="rect", xref="x", yref="y",
            x0=start, x1=end, y0=row.Bottom, y1=row.Top,
            line=dict(width=0), fillcolor=color, layer="below",
        ))
    return shapes


def _shapes_for_order_blocks(snap: SMCSnapshot, df_index) -> list[dict]:
    import pandas as pd
    shapes: list[dict] = []
    if snap.order_blocks.empty:
        return shapes
    last_ts = df_index[-1]
    for pos, row in enumerate(snap.order_blocks.itertuples(index=False)):
        if row.OB not in (1, -1):
            continue
        if pos >= len(df_index):
            continue
        start = df_index[pos]
        mit_idx = getattr(row, "MitigatedIndex", None)
        if mit_idx is not None and pd.notna(mit_idx):
            mit_idx = int(mit_idx)
            end = df_index[mit_idx] if mit_idx < len(df_index) else last_ts
        else:
            end = last_ts
        color = "rgba(70, 130, 180, 0.25)" if row.OB == 1 else "rgba(255, 140, 0, 0.25)"
        shapes.append(dict(
            type="rect", xref="x", yref="y",
            x0=start, x1=end, y0=row.Bottom, y1=row.Top,
            line=dict(color="rgba(0,0,0,0.4)", width=1, dash="dot"),
            fillcolor=color, layer="below",
        ))
    return shapes


def _annotations_for_bos(snap: SMCSnapshot, df_index) -> list[dict]:
    if snap.bos_choch.empty:
        return []
    out: list[dict] = []
    for pos, row in enumerate(snap.bos_choch.itertuples(index=False)):
        if pos >= len(df_index):
            continue
        for col, label in (("BOS", "BOS"), ("CHOCH", "CHoCH")):
            v = getattr(row, col, None)
            if v in (1, -1):
                y = getattr(row, "Level", None)
                if y is None:
                    continue
                out.append(dict(
                    x=df_index[pos], y=y, xref="x", yref="y",
                    text=f"{label}{'↑' if v == 1 else '↓'}",
                    showarrow=False,
                    font=dict(size=10, color="#ddd"),
                    bgcolor="rgba(0,0,0,0.5)",
                ))
    return out


def _scatter_for_signals(signals: Sequence[Signal]) -> list[go.Scatter]:
    bull_x: list = [s.detected_at for s in signals if s.direction is Direction.BULLISH]
    bull_y: list = [s.range_low for s in signals if s.direction is Direction.BULLISH]
    bull_text: list = [
        f"{s.subtype.value} (conf {s.confidence:.2f})"
        for s in signals if s.direction is Direction.BULLISH
    ]
    bear_x = [s.detected_at for s in signals if s.direction is Direction.BEARISH]
    bear_y = [s.range_high for s in signals if s.direction is Direction.BEARISH]
    bear_text = [
        f"{s.subtype.value} (conf {s.confidence:.2f})"
        for s in signals if s.direction is Direction.BEARISH
    ]
    out: list[go.Scatter] = []
    if bull_x:
        out.append(go.Scatter(
            x=bull_x, y=bull_y, mode="markers+text", name="Bullish CRT",
            marker=dict(symbol="triangle-up", size=14, color="lime",
                        line=dict(color="darkgreen", width=1)),
            text=["▲"] * len(bull_x),
            textposition="bottom center",
            hovertext=bull_text, hoverinfo="text",
        ))
    if bear_x:
        out.append(go.Scatter(
            x=bear_x, y=bear_y, mode="markers+text", name="Bearish CRT",
            marker=dict(symbol="triangle-down", size=14, color="red",
                        line=dict(color="darkred", width=1)),
            text=["▼"] * len(bear_x),
            textposition="top center",
            hovertext=bear_text, hoverinfo="text",
        ))
    return out


def render_chart(
    candles: Sequence[Candle],
    signals: Sequence[Signal] = (),
    *,
    title: str = "",
    swing_length: int = 10,
) -> go.Figure:
    """Build a Plotly Figure of `candles` with SMC overlays and CRT markers."""
    import pandas as pd  # noqa: F401  (used by the _shapes_* helpers below)

    snap = compute(candles, swing_length=swing_length)
    df = snap.df

    fig = make_subplots(rows=1, cols=1, vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
    ))

    # Swing markers (smc gives a RangeIndex aligned positionally to df.index)
    if not snap.swings.empty:
        sw = snap.swings.reset_index(drop=True)
        high_pos = [i for i, v in enumerate(sw["HighLow"]) if v == 1]
        low_pos = [i for i, v in enumerate(sw["HighLow"]) if v == -1]
        if high_pos:
            fig.add_trace(go.Scatter(
                x=[df.index[i] for i in high_pos],
                y=[sw["Level"].iloc[i] for i in high_pos],
                mode="markers",
                marker=dict(symbol="circle", color="#7e57c2", size=8,
                            line=dict(color="white", width=1)),
                name="Swing High",
            ))
        if low_pos:
            fig.add_trace(go.Scatter(
                x=[df.index[i] for i in low_pos],
                y=[sw["Level"].iloc[i] for i in low_pos],
                mode="markers",
                marker=dict(symbol="circle", color="#26c6da", size=8,
                            line=dict(color="white", width=1)),
                name="Swing Low",
            ))

    # Liquidity sweep lines
    if not snap.liquidity.empty:
        for pos, row in enumerate(snap.liquidity.itertuples(index=False)):
            if row.Liquidity not in (1, -1) or pos >= len(df.index):
                continue
            start = df.index[pos]
            end_idx = getattr(row, "End", None)
            if end_idx is not None and pd.notna(end_idx):
                end_idx = int(end_idx)
                end = df.index[end_idx] if end_idx < len(df.index) else df.index[-1]
            else:
                end = df.index[-1]
            color = "rgba(255,193,7,0.7)"
            fig.add_shape(
                type="line", xref="x", yref="y",
                x0=start, x1=end, y0=row.Level, y1=row.Level,
                line=dict(color=color, width=1, dash="dash"),
            )

    # CRT signal arrows
    for trace in _scatter_for_signals(signals):
        fig.add_trace(trace)

    fig.update_layout(
        title=title or "CRT scan",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=720,
        margin=dict(l=40, r=40, t=60, b=40),
        shapes=_shapes_for_fvgs(snap, df.index) + _shapes_for_order_blocks(snap, df.index),
        annotations=_annotations_for_bos(snap, df.index),
        legend=dict(orientation="h", y=1.05),
    )
    return fig


def write_chart_html(
    candles: Sequence[Candle],
    signals: Sequence[Signal],
    out_path: Path,
    *,
    title: str = "",
    refresh_seconds: int = 0,
) -> Path:
    """Render a chart to HTML on disk. If `refresh_seconds` > 0, the page
    auto-reloads at that interval so the same URL stays live."""
    fig = render_chart(candles, signals, title=title)
    html = fig.to_html(full_html=True, include_plotlyjs="cdn")
    if refresh_seconds > 0:
        meta = f'<meta http-equiv="refresh" content="{refresh_seconds}">'
        html = html.replace("<head>", f"<head>\n{meta}", 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
