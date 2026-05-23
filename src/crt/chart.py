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

from crt.context.smt import SMTReading, SMTState
from crt.detector.kod import KODSignal
from crt.models import Candle, Direction, PaperPosition, PositionStatus, Signal
from crt.smc import SMCSnapshot, compute
from crt.trade_plan import SetupCard, TradePlan


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


def _position_shapes_and_annotations(
    positions: Sequence[PaperPosition],
    last_ts,
    failure_tagger=None,
) -> tuple[list[dict], list[dict]]:
    """Draw each FILLED paper position's entry / SL / TP rails plus a close
    marker. Pending orders that expired or were cancelled before fill are
    skipped — they never traded so showing rails for them is just noise."""
    shapes: list[dict] = []
    annotations: list[dict] = []
    SKIP_STATES = {
        PositionStatus.PENDING,
        PositionStatus.PENDING_EXPIRED,
        PositionStatus.PENDING_CANCELLED,
    }
    for pos in positions:
        if pos.status in SKIP_STATES:
            continue
        x0 = pos.filled_at or pos.opened_at
        x1 = pos.closed_at or last_ts
        # Entry rail (blue dashed)
        shapes.append(dict(
            type="line", xref="x", yref="y",
            x0=x0, x1=x1, y0=pos.entry_price, y1=pos.entry_price,
            line=dict(color="rgba(100, 181, 246, 0.85)", width=1, dash="dot"),
        ))
        # Stop loss (red solid)
        shapes.append(dict(
            type="line", xref="x", yref="y",
            x0=x0, x1=x1, y0=pos.stop_loss, y1=pos.stop_loss,
            line=dict(color="rgba(239, 83, 80, 0.85)", width=1.2),
        ))
        # Take profits — TP1 amber, TP2 green, TP3 lighter green if present
        tp_colors = ["rgba(255, 193, 7, 0.85)",
                     "rgba(38, 198, 218, 0.85)",
                     "rgba(102, 187, 106, 0.65)"]
        for i, tp in enumerate(pos.take_profits[:3]):
            shapes.append(dict(
                type="line", xref="x", yref="y",
                x0=x0, x1=x1, y0=tp, y1=tp,
                line=dict(color=tp_colors[i], width=1, dash="dash"),
            ))
        # Close marker + status text
        status = pos.status
        if status == PositionStatus.CLOSED_TP:
            close_color = "#26a69a"
            close_label = "TP"
        elif status == PositionStatus.CLOSED_SL:
            close_color = "#ef5350"
            close_label = "SL"
            if failure_tagger is not None:
                tag = failure_tagger(pos)
                close_label = f"SL · {tag.mode.value}"
        elif status in (PositionStatus.OPEN, PositionStatus.TP1):
            close_color = "#ffb74d"
            close_label = status.value
        else:
            close_color = "#90a4ae"
            close_label = status.value
        anchor_y = pos.entry_price
        annotations.append(dict(
            x=x1, y=anchor_y, xref="x", yref="y",
            text=f"<b>{close_label}</b><br>{pos.realized_pnl:+.2f}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
            arrowcolor=close_color,
            ax=20, ay=-30,
            font=dict(size=10, color="#fff"),
            bgcolor=close_color, bordercolor=close_color, borderpad=2,
        ))
    return shapes, annotations


def _trade_plan_shapes_and_annotations(
    plan: TradePlan,
    sig: Signal,
    df_index,
    *,
    ghost: bool = False,
    x1=None,
) -> tuple[list[dict], list[dict]]:
    """Render a TradePlan as TradingView-style RISK / REWARD boxes plus
    R-multiple labels along the right edge.

    `ghost=True` dims everything for *past* plans so the active plan
    still pops while history stays visible.
    """
    shapes: list[dict] = []
    annotations: list[dict] = []
    if len(df_index) == 0:
        return shapes, annotations
    x0 = sig.detected_at
    if x1 is None:
        x1 = df_index[-1]
    bull = plan.direction is Direction.BULLISH

    alpha_mult = 0.35 if ghost else 1.0

    risk_top = max(plan.entry, plan.stop)
    risk_bot = min(plan.entry, plan.stop)
    shapes.append(dict(
        type="rect", xref="x", yref="y",
        x0=x0, x1=x1, y0=risk_bot, y1=risk_top,
        line=dict(color=f"rgba(239, 83, 80, {0.7 * alpha_mult})",
                  width=1, dash="dash" if ghost else "solid"),
        fillcolor=f"rgba(239, 83, 80, {0.15 * alpha_mult})", layer="below",
    ))

    if plan.targets:
        far_tp = plan.targets[-1]
        rew_top = max(plan.entry, far_tp)
        rew_bot = min(plan.entry, far_tp)
        shapes.append(dict(
            type="rect", xref="x", yref="y",
            x0=x0, x1=x1, y0=rew_bot, y1=rew_top,
            line=dict(color=f"rgba(38, 198, 218, {0.7 * alpha_mult})",
                      width=1, dash="dash" if ghost else "solid"),
            fillcolor=f"rgba(76, 175, 80, {0.13 * alpha_mult})", layer="below",
        ))

    # R-multiple gridlines + labels — only on the active plan to keep the
    # right gutter readable when many plans stack up.
    if not ghost:
        for tp, r in zip(plan.targets, plan.r_multiples):
            shapes.append(dict(
                type="line", xref="x", yref="y",
                x0=x0, x1=x1, y0=tp, y1=tp,
                line=dict(color="rgba(255, 255, 255, 0.18)", width=1, dash="dot"),
            ))
            annotations.append(dict(
                x=x1, y=tp, xref="x", yref="y",
                text=f"<b>{r:.2f}R</b>",
                showarrow=False, xanchor="right", yanchor="middle",
                font=dict(size=10, color="#fff"),
                bgcolor="rgba(38, 198, 218, 0.55)",
                bordercolor="rgba(38, 198, 218, 0.9)", borderpad=2,
            ))

    plan_label = "SHORT PLAN" if not bull else "LONG PLAN"
    status = "ACTIVE" if not ghost else "CLOSED"
    header_y = risk_top if not bull else risk_bot
    if not ghost:
        tp_summary = " | ".join(
            f"TP{i + 1} {r:.2f}R" for i, r in enumerate(plan.r_multiples)
        )
        annotations.append(dict(
            x=x0, y=header_y, xref="x", yref="y",
            text=f"<b>{plan_label} | {status}</b><br>{tp_summary}",
            showarrow=False, xanchor="left",
            yanchor="bottom" if not bull else "top",
            font=dict(size=11, color="#fff"),
            bgcolor="rgba(0, 0, 0, 0.65)",
            bordercolor="rgba(255, 255, 255, 0.25)", borderpad=4,
        ))
    return shapes, annotations


def _setup_card_annotation(card: SetupCard) -> dict:
    """Render the SetupCard as a single multi-line annotation pinned to
    the bottom-right corner — matches the TradingView CRT PRO+ table.
    """
    rows = card.to_table_rows()
    width = max(len(label) for label, _ in rows) + 2
    lines = [
        f"<b>* CRT PRO+</b>",
        f"<span style='font-size:10px'>{card.symbol}</span>",
        "",
    ]
    for label, value in rows:
        # Colorise BULL+ / BEAR- alignment cells
        if value.startswith("BULL"):
            value_html = f"<span style='color:#56d364'>{value}</span>"
        elif value.startswith("BEAR"):
            value_html = f"<span style='color:#f85149'>{value}</span>"
        else:
            value_html = value
        lines.append(f"{label:<{width}}: {value_html}")
    text = "<br>".join(lines)
    return dict(
        xref="paper", yref="paper", x=1.0, y=0.0,
        xanchor="right", yanchor="bottom",
        showarrow=False, align="left",
        text=text,
        font=dict(size=10, color="#e6edf3", family="ui-monospace, Menlo, monospace"),
        bgcolor="rgba(13, 17, 23, 0.92)",
        bordercolor="rgba(88, 166, 255, 0.55)", borderpad=6, borderwidth=1,
    )


def _signal_label(sig: Signal) -> str:
    """Hover text combining subtype, confidence and confluence breakdown."""
    parts = [
        f"{sig.subtype.value}",
        f"conf {sig.confidence:.2f}",
        f"confluence {sig.confluence_score:+.1f}",
    ]
    if sig.confluence_breakdown:
        breakdown = ", ".join(
            f"{k}:{v:+.1f}" for k, v in sig.confluence_breakdown.items()
        )
        parts.append(breakdown)
    return " · ".join(parts)


def _scatter_for_signals(signals: Sequence[Signal]) -> list[go.Scatter]:
    """Split signals into CRT-style and Model #1 traces with distinct markers."""
    out: list[go.Scatter] = []

    def _grouped(direction: Direction, *, is_model1: bool):
        sigs = [
            s for s in signals
            if s.direction is direction
            and (s.subtype.value == "model_1_single_trigger") == is_model1
        ]
        return sigs

    # CRT-classic markers: solid triangles
    for direction, color, dark, symbol, name in (
        (Direction.BULLISH, "lime", "darkgreen", "triangle-up", "Bullish CRT"),
        (Direction.BEARISH, "red", "darkred", "triangle-down", "Bearish CRT"),
    ):
        sigs = _grouped(direction, is_model1=False)
        if not sigs:
            continue
        y_attr = "range_low" if direction is Direction.BULLISH else "range_high"
        out.append(go.Scatter(
            x=[s.detected_at for s in sigs],
            y=[getattr(s, y_attr) for s in sigs],
            mode="markers", name=name,
            marker=dict(symbol=symbol, size=14, color=color,
                        line=dict(color=dark, width=1)),
            hovertext=[_signal_label(s) for s in sigs], hoverinfo="text",
        ))

    # Model #1 markers: star symbol so they stand out from CRT triangles
    for direction, color, dark, name in (
        (Direction.BULLISH, "#80deea", "#006064", "Bullish Model #1"),
        (Direction.BEARISH, "#ff8a65", "#bf360c", "Bearish Model #1"),
    ):
        sigs = _grouped(direction, is_model1=True)
        if not sigs:
            continue
        out.append(go.Scatter(
            x=[s.detected_at for s in sigs],
            y=[s.entry_override or s.lhf for s in sigs],
            mode="markers", name=name,
            marker=dict(symbol="star", size=15, color=color,
                        line=dict(color=dark, width=1)),
            hovertext=[_signal_label(s) for s in sigs], hoverinfo="text",
        ))
    return out


def render_chart(
    candles: Sequence[Candle],
    signals: Sequence[Signal] = (),
    kods: Sequence[KODSignal] = (),
    smt_reading: SMTReading | None = None,
    positions: Sequence[PaperPosition] = (),
    failure_tagger=None,
    trade_plans: Sequence[tuple[Signal, TradePlan]] = (),
    setup_card: SetupCard | None = None,
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

    # KOD spike markers: golden diamond on the spike candle
    if kods:
        bull_kods = [k for k in kods if k.direction is Direction.BULLISH]
        bear_kods = [k for k in kods if k.direction is Direction.BEARISH]
        if bull_kods:
            fig.add_trace(go.Scatter(
                x=[k.kod_candle.open_time for k in bull_kods],
                y=[k.kod_candle.low for k in bull_kods],
                mode="markers", name="Bullish KOD",
                marker=dict(symbol="diamond", size=12, color="gold",
                            line=dict(color="darkgoldenrod", width=1)),
                hovertext=[f"KOD spike @ {k.spike_price:.6f}" for k in bull_kods],
                hoverinfo="text",
            ))
        if bear_kods:
            fig.add_trace(go.Scatter(
                x=[k.kod_candle.open_time for k in bear_kods],
                y=[k.kod_candle.high for k in bear_kods],
                mode="markers", name="Bearish KOD",
                marker=dict(symbol="diamond", size=12, color="gold",
                            line=dict(color="darkgoldenrod", width=1)),
                hovertext=[f"KOD spike @ {k.spike_price:.6f}" for k in bear_kods],
                hoverinfo="text",
            ))

    # Per-signal annotations: confluence score floats above each marker
    extra_annotations: list[dict] = []
    extra_shapes: list[dict] = []
    for s in signals:
        is_model1 = s.subtype.value == "model_1_single_trigger"
        if s.confluence_score:
            color = ("#26a69a" if s.confluence_score >= 5
                     else "#ffb74d" if s.confluence_score >= 1
                     else "#ef5350")
            y_anchor = (s.range_high if s.direction is Direction.BEARISH
                        else s.range_low)
            offset = 1.02 if s.direction is Direction.BEARISH else 0.98
            extra_annotations.append(dict(
                x=s.detected_at, y=y_anchor * offset, xref="x", yref="y",
                text=f"<b>{s.confluence_score:+.0f}</b>",
                showarrow=False,
                font=dict(size=11, color=color),
                bgcolor="rgba(0,0,0,0.55)",
                bordercolor=color, borderwidth=1, borderpad=2,
            ))
        # Model #1: draw a small box around the trigger candle's body so
        # the operator can spot the thick candle context at a glance.
        if is_model1 and s.entry_override is not None and s.stop_override is not None:
            color = ("rgba(38, 198, 218, 0.45)" if s.direction is Direction.BULLISH
                     else "rgba(255, 140, 0, 0.45)")
            extra_shapes.append(dict(
                type="line", xref="x", yref="y",
                x0=s.detected_at, x1=s.detected_at,
                y0=s.stop_override, y1=s.entry_override,
                line=dict(color=color, width=3),
            ))

    # Trade plans (risk/reward boxes + R-multiple labels). The LAST plan
    # in the list is treated as ACTIVE; earlier plans render as ghosts so
    # the operator can still see past structure on the chart.
    plan_list = list(trade_plans)
    for i, (plan_sig, plan) in enumerate(plan_list):
        is_active = (i == len(plan_list) - 1)
        # Ghost plans only extend up to the *next* plan's detected_at so
        # the chart doesn't get smothered in stacked boxes.
        if is_active:
            ghost_x1 = None
        else:
            next_sig = plan_list[i + 1][0]
            ghost_x1 = next_sig.detected_at
        plan_shapes, plan_annotations = _trade_plan_shapes_and_annotations(
            plan, plan_sig, df.index, ghost=not is_active, x1=ghost_x1,
        )
        extra_shapes.extend(plan_shapes)
        extra_annotations.extend(plan_annotations)

    # Setup card pinned to the bottom-right corner
    if setup_card is not None:
        extra_annotations.append(_setup_card_annotation(setup_card))

    full_title = title or "CRT scan"
    if smt_reading is not None and smt_reading.is_divergent:
        flag = "🐂" if smt_reading.state is SMTState.BULLISH else "🐻"
        full_title += (
            f"   ·   {flag} SMT vs {smt_reading.pair_symbol}: "
            f"{smt_reading.state.value}"
        )

    pos_shapes, pos_annotations = _position_shapes_and_annotations(
        positions, df.index[-1], failure_tagger,
    )
    fig.update_layout(
        title=full_title,
        xaxis_rangeslider_visible=False,
        xaxis=dict(range=[df.index[0], df.index[-1]]) if len(df) else None,
        template="plotly_dark",
        height=720,
        margin=dict(l=40, r=40, t=60, b=40),
        shapes=(_shapes_for_fvgs(snap, df.index)
                + _shapes_for_order_blocks(snap, df.index)
                + extra_shapes
                + pos_shapes),
        annotations=(_annotations_for_bos(snap, df.index)
                     + extra_annotations
                     + pos_annotations),
        legend=dict(orientation="h", y=1.05),
    )
    return fig


def write_chart_html(
    candles: Sequence[Candle],
    signals: Sequence[Signal],
    out_path: Path,
    kods: Sequence[KODSignal] = (),
    smt_reading: SMTReading | None = None,
    positions: Sequence[PaperPosition] = (),
    failure_tagger=None,
    trade_plans: Sequence[tuple[Signal, TradePlan]] = (),
    setup_card: SetupCard | None = None,
    *,
    title: str = "",
    refresh_seconds: int = 0,
) -> Path:
    """Render a chart to HTML on disk. If `refresh_seconds` > 0, the page
    auto-reloads at that interval so the same URL stays live."""
    fig = render_chart(
        candles, signals, kods=kods, smt_reading=smt_reading,
        positions=positions, failure_tagger=failure_tagger,
        trade_plans=trade_plans, setup_card=setup_card,
        title=title,
    )
    html = fig.to_html(full_html=True, include_plotlyjs="cdn")
    if refresh_seconds > 0:
        meta = f'<meta http-equiv="refresh" content="{refresh_seconds}">'
        html = html.replace("<head>", f"<head>\n{meta}", 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
