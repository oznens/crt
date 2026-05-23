# CRT — Candle Range Theory terminal

A scanner + paper-trading terminal for crypto markets, built around the
[Candle Range Theory](docs/notes/crt.md) framework (Timon / ICT University).

This repo is in heavy development. The current focus is:

1. Ingest Bybit V5 linear perpetuals market data (REST bootstrap + WS live stream).
2. Detect all 5 CRT subtypes via a generic state machine.
3. Project DOL ladders (LHF → Initial DOL → Extended DOL) for each signal.
4. Paper-trade the signals to validate edge before going live.
5. Surface everything in a Rich TUI dashboard.

## Layout

```
src/crt/
├── data/        # Bybit client (REST + WS); MEXC client kept as a legacy fallback
├── store/       # In-memory candle ringbuffer
├── detector/    # CRT subtype state machine
├── context/     # HTF→LTF alignment, time windows, IPDA/IRL-ERL filters
├── signal/      # DOL ladder post-processing
├── paper/       # Paper trading engine
├── tui/         # Rich dashboard
├── cli.py       # `crt` entry point
└── runtime.py   # Async glue: stream → store → detector → paper → TUI
```

Reference material:

- `docs/notes/crt.md` — distilled CRT knowledge base (live document).
- `docs/pdfs/` — source PDFs.

## Run (when deps installed)

```bash
pip install -e .[dev]

# Live scanner (default): top 50 Bybit USDT linear perps by 24h turnover
crt scan --tf 15m 1h 4h

# Pin an explicit watchlist (canonical underscore form; Bybit's BTCUSDT is normalised)
crt scan --symbols BTC_USDT ETH_USDT SOL_USDT --tf 15m 1h 4h

# Smaller universe
crt scan --top 30 --tf 15m 1h

# Tighter signal filtering (NY kill-zone only)
crt scan --min-tier high --strict-htf

# Backtest the last N bars per (symbol, tf) and print a summary report
crt backtest --top 20 --tf 1h --bars 1000

# Parallel backtest across the top-50 universe (concurrent REST fetches)
crt backtest --top 50 --tf 1h --bars 1000 --parallel --concurrency 8

# Render a single-symbol Plotly chart with SMC overlays (FVG, OB, BOS, swings)
# and CRT signal markers; open the HTML in any browser
crt chart BTC_USDT --tf 1h --bars 500 --out chart.html

# Same, but re-render every 60s so the browser auto-reloads via meta-refresh
crt chart BTC_USDT --tf 15m --watch 60
```

## SMC integration

The chart command uses [`smartmoneyconcepts`](https://github.com/joshyattridge/smart-money-concepts)
under the hood. The same library is exposed via `crt.smc` so any of its
indicators (FVG, swing highs/lows, BOS/CHoCH, order blocks, liquidity,
previous high/low, sessions, retracements) can be reused inside the
detector and confluence stacker.

## Tests

```bash
pytest -q
```
