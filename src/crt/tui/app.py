"""Rich-based live dashboard.

Layout:
    ┌─────────────── Watchlist ───────────────┬──── Recent signals ────┐
    │ symbol  tf   last    state              │ when sym tf type ...   │
    ├─────────────────────────────────────────┼─────────────────────────┤
    │              Paper positions (open)     │ Closed P&L summary     │
    └─────────────────────────────────────────┴─────────────────────────┘
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Iterable

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from crt.models import PaperPosition, PositionStatus, Signal, Timeframe
from crt.paper import PaperEngine
from crt.store import CandleStore


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


class Dashboard:
    def __init__(
        self,
        store: CandleStore,
        engine: PaperEngine,
        watch: Iterable[tuple[str, Timeframe]],
        max_signals: int = 25,
    ):
        self.store = store
        self.engine = engine
        self.watch = list(watch)
        self.recent_signals: deque[Signal] = deque(maxlen=max_signals)
        self._console = Console()

    # public hook used by runtime
    def push_signal(self, signal: Signal) -> None:
        self.recent_signals.append(signal)

    def _watchlist_panel(self) -> Panel:
        table = Table(expand=True, show_header=True, header_style="bold cyan")
        table.add_column("Symbol")
        table.add_column("TF")
        table.add_column("Last", justify="right")
        table.add_column("Chg %", justify="right")
        table.add_column("Body", justify="right")
        for sym, tf in self.watch:
            candles = self.store.get(sym, tf, count=2)
            if len(candles) < 2:
                table.add_row(sym, tf.value, "-", "-", "-")
                continue
            cur, prev = candles[-1], candles[-2]
            chg = (cur.close - prev.close) / prev.close * 100 if prev.close else 0.0
            chg_style = "green" if chg >= 0 else "red"
            table.add_row(
                sym, tf.value,
                _fmt(cur.close, 4),
                f"[{chg_style}]{chg:+.2f}[/{chg_style}]",
                _fmt(cur.body, 4),
            )
        return Panel(table, title="Watchlist", border_style="cyan")

    def _signals_panel(self) -> Panel:
        table = Table(expand=True, show_header=True, header_style="bold magenta")
        table.add_column("When")
        table.add_column("Symbol")
        table.add_column("TF")
        table.add_column("Dir")
        table.add_column("Type")
        table.add_column("CRH", justify="right")
        table.add_column("CRL", justify="right")
        table.add_column("Conf", justify="right")
        for s in reversed(self.recent_signals):
            dir_style = "green" if s.direction.value == "bullish" else "red"
            table.add_row(
                _fmt_dt(s.detected_at),
                s.symbol,
                s.tf.value,
                f"[{dir_style}]{s.direction.value[:4]}[/{dir_style}]",
                s.subtype.value.split("_", 2)[-1],
                _fmt(s.range_high, 4),
                _fmt(s.range_low, 4),
                f"{s.confidence:.2f}",
            )
        return Panel(table, title="Signals", border_style="magenta")

    def _positions_panel(self) -> Panel:
        table = Table(expand=True, show_header=True, header_style="bold yellow")
        table.add_column("Symbol")
        table.add_column("TF")
        table.add_column("Dir")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP1/2/3", justify="right")
        table.add_column("Status")
        table.add_column("uPnL", justify="right")
        for pos in self.engine.open_positions:
            tps = "/".join(_fmt(t, 4) for t in pos.take_profits)
            pnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
            table.add_row(
                pos.signal.symbol,
                pos.signal.tf.value,
                pos.side.value[:4],
                _fmt(pos.entry_price, 4),
                _fmt(pos.stop_loss, 4),
                tps,
                pos.status.value,
                f"[{pnl_style}]{pos.unrealized_pnl:+.2f}[/{pnl_style}]",
            )
        return Panel(table, title="Open positions", border_style="yellow")

    def _summary_panel(self) -> Panel:
        closed = self.engine.closed_positions
        wins = sum(1 for p in closed if p.status == PositionStatus.CLOSED_TP)
        losses = sum(1 for p in closed if p.status == PositionStatus.CLOSED_SL)
        wr = (wins / (wins + losses) * 100) if (wins + losses) else 0.0
        total_pnl = sum(p.realized_pnl for p in closed)
        lines = [
            f"Balance: [bold]{self.engine.balance:.2f}[/bold]",
            f"Realized PnL: [{'green' if total_pnl >= 0 else 'red'}]{total_pnl:+.2f}[/]",
            f"Closed: {len(closed)}  W: {wins}  L: {losses}  WR: {wr:.1f}%",
            f"Open: {len(self.engine.open_positions)}",
        ]
        return Panel(Group(*lines), title="P&L", border_style="green")

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="top", ratio=2),
            Layout(name="bottom", ratio=2),
        )
        layout["top"].split_row(
            Layout(self._watchlist_panel(), name="watch"),
            Layout(self._signals_panel(), name="sig"),
        )
        layout["bottom"].split_row(
            Layout(self._positions_panel(), name="pos", ratio=3),
            Layout(self._summary_panel(), name="pnl", ratio=1),
        )
        return layout

    def live(self) -> Live:
        return Live(
            self.render(),
            console=self._console,
            refresh_per_second=2,
            screen=True,
            auto_refresh=False,
        )
