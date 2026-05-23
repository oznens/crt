"""FastAPI app exposing the live runtime state.

Endpoints:

  GET /            HTML dashboard (watchlist + signals + positions + chart)
  GET /api/state   JSON snapshot of watchlist / signals / positions / pnl
  GET /api/chart   Plotly figure JSON for a specific (symbol, tf)

The HTML page polls /api/state at a configurable cadence and re-renders
the Plotly chart inline. No JS framework — just plain fetch() in a small
embedded script. Keeps deployment friction at zero.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Iterable

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from datetime import timedelta

from crt.chart import render_chart
from crt.context import SMTMonitor, evaluate_cisd, parent_tf, score_signal
from crt.context.cisd import CISDStatus
from crt.detector import detect_kod
from crt.models import Direction, PaperPosition, PositionStatus, Signal, Timeframe
from crt.paper import PaperEngine, classify as classify_failure
from crt.smc import compute as compute_smc
from crt.store import CandleStore
from crt.trade_plan import SetupCard, TradePlan


def _signal_to_json(s: Signal) -> dict:
    return {
        "symbol": s.symbol,
        "tf": s.tf.value,
        "subtype": s.subtype.value,
        "direction": s.direction.value,
        "detected_at": s.detected_at.isoformat(),
        "range_high": s.range_high,
        "range_low": s.range_low,
        "confidence": s.confidence,
        "confluence": s.confluence_score,
        "breakdown": s.confluence_breakdown,
        "note": s.note,
    }


def _position_to_json(p: PaperPosition) -> dict:
    return {
        "symbol": p.signal.symbol,
        "tf": p.signal.tf.value,
        "side": p.side.value,
        "entry": p.entry_price,
        "stop": p.stop_loss,
        "tps": p.take_profits,
        "status": p.status.value,
        "opened_at": p.opened_at.isoformat(),
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        "pnl": p.realized_pnl if p.status != PositionStatus.OPEN else p.unrealized_pnl,
    }


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>CRT live</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { font: 13px/1.4 ui-monospace,Menlo,Consolas,monospace;
         background: #0d1117; color: #e6edf3; margin: 0; padding: 12px; }
  h1 { font-size: 16px; margin: 0 0 8px; color: #58a6ff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .panel { background: #161b22; border: 1px solid #30363d;
           border-radius: 6px; padding: 10px; }
  .full { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 4px 6px; border-bottom: 1px solid #21262d; text-align: left; }
  th { color: #8b949e; font-weight: 500; text-transform: uppercase; font-size: 11px; }
  .pos { color: #56d364; }
  .neg { color: #f85149; }
  .chip { display: inline-block; padding: 1px 6px; border-radius: 4px;
          font-size: 11px; }
  .bull { background: #1f6f3a; color: #fff; }
  .bear { background: #b62324; color: #fff; }
  #chart { height: 560px; }
  .balance { font-size: 20px; font-weight: 600; }
  .muted { color: #8b949e; }
  input, button, select {
    background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 4px; padding: 4px 8px; font: inherit;
  }
</style>
</head>
<body>
  <h1>CRT live · <span class="muted" id="last-update"></span></h1>

  <div class="grid">
    <div class="panel">
      <table>
        <thead><tr><th>Symbol</th><th>TF</th><th>Last</th><th>Chg%</th></tr></thead>
        <tbody id="watchlist"></tbody>
      </table>
    </div>

    <div class="panel">
      <div class="balance" id="balance">—</div>
      <div class="muted" id="pnl-summary"></div>
    </div>

    <div class="panel full">
      <strong>Recent signals</strong>
      <table>
        <thead><tr>
          <th>Time</th><th>Symbol</th><th>TF</th><th>Dir</th><th>Type</th>
          <th>CRH</th><th>CRL</th><th>Conf</th><th>Confl</th>
        </tr></thead>
        <tbody id="signals"></tbody>
      </table>
    </div>

    <div class="panel full">
      <strong>Open positions</strong>
      <table>
        <thead><tr>
          <th>Symbol</th><th>TF</th><th>Side</th><th>Entry</th><th>Stop</th>
          <th>TPs</th><th>Status</th><th>uPnL</th>
        </tr></thead>
        <tbody id="positions"></tbody>
      </table>
    </div>

    <div class="panel full">
      <div style="margin-bottom: 6px;">
        <span class="muted">Chart symbol:</span>
        <input id="chart-symbol" value="BTC_USDT" style="width:120px" />
        <select id="chart-tf">
          <option>1m</option><option>5m</option><option selected>15m</option>
          <option>1h</option><option>4h</option><option>1d</option>
        </select>
        <button onclick="refreshChart()">Render</button>
      </div>
      <div id="chart"></div>
    </div>

    <div class="panel full">
      <strong>Backtest</strong>
      <div style="margin: 6px 0;">
        <span class="muted">Symbols (comma-separated):</span>
        <input id="bt-symbols" value="BTC_USDT,ETH_USDT,SOL_USDT"
               style="width:340px" />
        <span class="muted">TF:</span>
        <select id="bt-tf">
          <option>15m</option><option selected>1h</option>
          <option>4h</option><option>1d</option>
        </select>
        <span class="muted">Bars:</span>
        <input id="bt-bars" type="number" value="500" style="width:80px" />
        <span class="muted">Risk $:</span>
        <input id="bt-risk" type="number" value="100" style="width:80px" />
        <button onclick="runBacktest()" id="bt-run">▶ Run backtest</button>
        <span id="bt-status" class="muted"></span>
      </div>
      <div id="bt-result"></div>
    </div>
  </div>

<script>
const REFRESH_MS = 4000;
function pad(n) { return ("0"+n).slice(-2); }
function fmtTime(iso) {
  const d = new Date(iso);
  return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}
function dirChip(d) {
  return `<span class="chip ${d==='bullish'?'bull':'bear'}">${d.slice(0,4)}</span>`;
}
async function refreshState() {
  const r = await fetch('/api/state');
  if (!r.ok) return;
  const s = await r.json();

  document.getElementById('last-update').textContent =
    'updated ' + new Date().toLocaleTimeString();

  document.getElementById('balance').textContent =
    'Balance: ' + s.balance.toFixed(2);
  document.getElementById('pnl-summary').innerHTML =
    `realized PnL <span class="${s.realized_pnl>=0?'pos':'neg'}">${s.realized_pnl.toFixed(2)}</span>
     · W:${s.wins} L:${s.losses} · WR ${s.win_rate.toFixed(1)}%`;

  document.getElementById('watchlist').innerHTML = s.watchlist.map(w =>
    `<tr><td>${w.symbol}</td><td>${w.tf}</td><td>${w.last}</td>
         <td class="${w.chg>=0?'pos':'neg'}">${w.chg.toFixed(2)}%</td></tr>`
  ).join('');

  document.getElementById('signals').innerHTML = s.signals.map(g =>
    `<tr>
       <td>${fmtTime(g.detected_at)}</td>
       <td>${g.symbol}</td><td>${g.tf}</td><td>${dirChip(g.direction)}</td>
       <td>${g.subtype.split('_').slice(-2).join('_')}</td>
       <td>${g.range_high.toFixed(4)}</td><td>${g.range_low.toFixed(4)}</td>
       <td>${g.confidence.toFixed(2)}</td>
       <td class="${g.confluence>=5?'pos':(g.confluence>=1?'':'neg')}">
         ${g.confluence.toFixed(1)}</td>
     </tr>`
  ).join('');

  document.getElementById('positions').innerHTML = s.positions.map(p =>
    `<tr>
       <td>${p.symbol}</td><td>${p.tf}</td>
       <td>${dirChip(p.side)}</td>
       <td>${p.entry.toFixed(4)}</td><td>${p.stop.toFixed(4)}</td>
       <td>${p.tps.map(t=>t.toFixed(4)).join('/')}</td>
       <td>${p.status}</td>
       <td class="${p.pnl>=0?'pos':'neg'}">${p.pnl.toFixed(2)}</td>
     </tr>`
  ).join('');
}
async function refreshChart() {
  const sym = document.getElementById('chart-symbol').value;
  const tf = document.getElementById('chart-tf').value;
  const r = await fetch(`/api/chart?symbol=${sym}&tf=${tf}`);
  if (!r.ok) { return; }
  const fig = await r.json();
  Plotly.react('chart', fig.data, fig.layout, {responsive:true});
}
async function runBacktest() {
  const symbols = document.getElementById('bt-symbols').value
    .split(',').map(s => s.trim()).filter(Boolean);
  const tf = document.getElementById('bt-tf').value;
  const bars = parseInt(document.getElementById('bt-bars').value, 10);
  const risk = parseFloat(document.getElementById('bt-risk').value);
  const btn = document.getElementById('bt-run');
  const status = document.getElementById('bt-status');
  const result = document.getElementById('bt-result');
  btn.disabled = true;
  status.textContent = ' · running ' + symbols.length + ' symbols × ' + bars + ' bars ...';
  result.innerHTML = '';
  try {
    const r = await fetch('/api/backtest', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({symbols, tfs: [tf], bars, risk}),
    });
    if (!r.ok) {
      const text = await r.text();
      status.textContent = ' · error: ' + text;
      return;
    }
    const d = await r.json();
    status.textContent = ' · done.';
    let html = `
      <table>
        <tr><th>Period</th><td>${d.symbols.length} symbols · ${d.tfs.join(',')} · ${d.bars} bars</td></tr>
        <tr><th>Balance</th><td>${d.starting_balance.toFixed(2)} → ${d.ending_balance.toFixed(2)}
            <span class="${d.pnl>=0?'pos':'neg'}">(${d.pnl>=0?'+':''}${d.pnl.toFixed(2)}, ${d.return_pct.toFixed(2)}%)</span></td></tr>
        <tr><th>Trades</th><td>${d.n_signals} signals · ${d.n_positions} positions
            · W ${d.wins} · L ${d.losses} · WR ${d.win_rate.toFixed(1)}%</td></tr>
        <tr><th>Avg win / loss</th><td>${d.avg_win.toFixed(2)} / ${d.avg_loss.toFixed(2)}
            · expectancy ${d.expectancy.toFixed(2)} · MDD ${d.max_drawdown.toFixed(2)}</td></tr>
      </table>`;
    if (Object.keys(d.by_subtype).length) {
      html += '<br><strong>By subtype</strong><table><tr><th>Subtype</th><th>Trades</th><th>W</th><th>L</th><th>PnL</th></tr>';
      for (const [st, b] of Object.entries(d.by_subtype)) {
        html += `<tr><td>${st}</td><td>${b.trades}</td><td>${b.wins}</td>
                 <td>${b.losses}</td><td class="${b.pnl>=0?'pos':'neg'}">${b.pnl.toFixed(2)}</td></tr>`;
      }
      html += '</table>';
    }
    if (Object.keys(d.by_confluence).length) {
      html += '<br><strong>By confluence bucket</strong><table><tr><th>Bucket</th><th>Trades</th><th>W</th><th>L</th><th>PnL</th></tr>';
      for (const [bk, b] of Object.entries(d.by_confluence)) {
        html += `<tr><td>${bk}</td><td>${b.trades}</td><td>${b.wins}</td>
                 <td>${b.losses}</td><td class="${b.pnl>=0?'pos':'neg'}">${b.pnl.toFixed(2)}</td></tr>`;
      }
      html += '</table>';
    }
    if (Object.keys(d.by_failure_mode).length) {
      html += '<br><strong>Failure modes (SL)</strong><table><tr><th>Mode</th><th>Trades</th><th>PnL</th></tr>';
      for (const [m, b] of Object.entries(d.by_failure_mode)) {
        html += `<tr><td>${m}</td><td>${b.trades}</td>
                 <td class="neg">${b.pnl.toFixed(2)}</td></tr>`;
      }
      html += '</table>';
    }
    result.innerHTML = html;
  } catch (e) {
    status.textContent = ' · error: ' + e;
  } finally {
    btn.disabled = false;
  }
}

refreshState();
refreshChart();
setInterval(refreshState, REFRESH_MS);
setInterval(refreshChart, REFRESH_MS * 4);
</script>
</body>
</html>
"""


class WebDashboard:
    """State container the FastAPI app reads from.

    Designed to be filled by `Runtime` — every closed candle the runtime
    processes optionally calls `push_signal()` and the FastAPI handlers
    surface that state to the browser.
    """

    def __init__(
        self,
        store: CandleStore,
        engine: PaperEngine,
        watch: Iterable[tuple[str, Timeframe]],
        max_signals: int = 50,
    ):
        self.store = store
        self.engine = engine
        self.watch = list(watch)
        self.recent_signals: deque[Signal] = deque(maxlen=max_signals)
        self.smt = SMTMonitor(store)

    def push_signal(self, s: Signal) -> None:
        self.recent_signals.append(s)

    # ----------------------------------------------- snapshot for /api/state

    def snapshot(self) -> dict:
        watchlist = []
        for sym, tf in self.watch:
            candles = self.store.get(sym, tf, count=2)
            if len(candles) < 2:
                watchlist.append({"symbol": sym, "tf": tf.value, "last": "—", "chg": 0.0})
                continue
            cur, prev = candles[-1], candles[-2]
            chg = (cur.close - prev.close) / prev.close * 100 if prev.close else 0.0
            watchlist.append({
                "symbol": sym, "tf": tf.value,
                "last": f"{cur.close:.4f}", "chg": chg,
            })

        closed = self.engine.closed_positions
        wins = sum(1 for p in closed if p.status == PositionStatus.CLOSED_TP)
        losses = sum(1 for p in closed if p.status == PositionStatus.CLOSED_SL)
        wr = wins / (wins + losses) * 100 if (wins + losses) else 0.0
        realized = sum(p.realized_pnl for p in closed)

        return {
            "balance": self.engine.balance,
            "realized_pnl": realized,
            "wins": wins,
            "losses": losses,
            "win_rate": wr,
            "watchlist": watchlist,
            "signals": [_signal_to_json(s) for s in reversed(self.recent_signals)],
            "positions": [_position_to_json(p) for p in self.engine.open_positions],
        }

    # --------------------------------------------- chart for /api/chart

    def chart_payload(self, symbol: str, tf: Timeframe) -> dict:
        candles = self.store.get(symbol, tf)
        if not candles:
            raise HTTPException(404, f"no candles for {symbol} {tf.value}")

        relevant_signals = [
            s for s in self.recent_signals
            if s.symbol == symbol and s.tf is tf
        ]
        kods = []
        for s in relevant_signals:
            after = [c for c in candles if c.open_time > s.detected_at]
            k = detect_kod(s, after)
            if k:
                kods.append(k)

        relevant_positions = [
            p for p in self.engine.open_positions + self.engine.closed_positions
            if p.signal.symbol == symbol and p.signal.tf is tf
        ]

        def _tagger(p):
            return classify_failure(p, self.store, self.smt)

        # Trade plans for the LAST signal (the active one) only — keeps
        # the chart from getting buried under risk/reward boxes when many
        # signals print on the same window.
        trade_plans: list[tuple[Signal, TradePlan]] = []
        setup_card: SetupCard | None = None
        smt_reading = None
        if relevant_signals:
            active = relevant_signals[-1]
            trade_plans.append((active, TradePlan.from_signal(active)))
            smt_reading = self.smt.reading(symbol, tf, active.direction)

            # Build the corner setup card.
            after = [c for c in candles if c.open_time > active.detected_at]
            cisd = evaluate_cisd(active, after)
            # Per-TF alignment across the full HTF ladder. Each cell uses
            # the most-recent CLOSED candle on that TF — that's the body
            # direction smart-money traders look at when stacking bias.
            alignment: dict[str, str] = {}
            for probe_tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1,
                             Timeframe.H4, Timeframe.D1, Timeframe.W1):
                probe_candles = self.store.get(symbol, probe_tf)
                if not probe_candles:
                    continue
                # The very last candle may still be forming; the previous
                # one is guaranteed closed.
                ref = probe_candles[-2] if len(probe_candles) > 1 else probe_candles[-1]
                tag = "BULL +" if ref.is_bullish else "BEAR -"
                alignment[probe_tf.value] = tag
            # Time-to-close: open_time + tf duration - now.
            last_candle = candles[-1]
            closes_at = last_candle.open_time + timedelta(seconds=tf.seconds)
            setup_card = SetupCard(
                symbol=symbol,
                ltf_tf=tf,
                htf_tf=parent_tf(tf),
                model="BULL" if active.direction is Direction.BULLISH else "BEAR",
                bias="LONG" if active.direction is Direction.BULLISH else "SHORT",
                level=active.range_high if active.direction is Direction.BEARISH
                      else active.range_low,
                c2_status="CONF",
                cisd_status=cisd.status,
                smt_pair=(f"{symbol}+{self.smt.pair_for(symbol)}"
                          if self.smt.pair_for(symbol) else None),
                smt_state=smt_reading.state if smt_reading else None,  # type: ignore[arg-type]
                tf_alignment=alignment,
                closes_at=closes_at,
                confluence=active.confluence_score,
            )

        fig = render_chart(
            candles, relevant_signals,
            kods=kods, smt_reading=smt_reading,
            positions=relevant_positions, failure_tagger=_tagger,
            trade_plans=trade_plans, setup_card=setup_card,
            title=f"{symbol} {tf.value}",
        )
        return json.loads(fig.to_json())


def create_app(dashboard: WebDashboard) -> FastAPI:
    app = FastAPI(title="CRT live")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _INDEX_HTML

    @app.get("/api/state")
    async def state():
        return JSONResponse(dashboard.snapshot())

    @app.get("/api/chart")
    async def chart(symbol: str, tf: str = "15m"):
        try:
            tf_enum = Timeframe(tf)
        except ValueError as e:
            raise HTTPException(400, f"unknown tf: {tf}") from e
        return JSONResponse(dashboard.chart_payload(symbol, tf_enum))

    @app.post("/api/backtest")
    async def backtest_endpoint(req: dict):
        """Run a fresh BacktestRunner over the requested symbols/TF/bars
        and return a JSON-shaped report. Used by the "Backtest" panel
        in the dashboard."""
        from crt.backtest import BacktestRunner
        from crt.data.bybit import BybitClient
        from crt.paper import PaperConfig

        symbols = req.get("symbols") or []
        if not symbols:
            raise HTTPException(400, "symbols list required")
        tfs = [Timeframe(t) for t in (req.get("tfs") or ["1h"])]
        bars = int(req.get("bars", 500))
        risk = float(req.get("risk", 100.0))
        balance = float(req.get("balance", 10_000.0))

        runner = BacktestRunner(
            symbols=symbols, timeframes=tfs,
            paper_config=PaperConfig(starting_balance=balance, risk_per_trade=risk),
        )
        async with BybitClient() as client:
            await runner.load_from_exchange(client, limit_per_tf=bars)
        report = runner.report()

        return JSONResponse({
            "symbols": symbols,
            "tfs": [t.value for t in tfs],
            "bars": bars,
            "starting_balance": report.starting_balance,
            "ending_balance": report.ending_balance,
            "pnl": report.total_pnl,
            "return_pct": report.return_pct,
            "wins": report.wins,
            "losses": report.losses,
            "win_rate": report.win_rate,
            "avg_win": report.avg_win,
            "avg_loss": report.avg_loss,
            "expectancy": report.expectancy,
            "max_drawdown": report.max_drawdown,
            "n_signals": len(report.signals),
            "n_positions": len(report.positions),
            "by_subtype": {
                st.value: b for st, b in report.by_subtype().items()
            },
            "by_failure_mode": {
                mode.value: b for mode, b in report.failure_breakdown.items()
            },
            "by_confluence": report.by_confluence_bucket(),
        })

    @app.get("/healthz")
    async def healthz():
        return Response("ok", media_type="text/plain")

    return app
