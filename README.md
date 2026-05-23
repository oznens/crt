# CRT — Candle Range Theory terminal

A scanner + paper-trading terminal for crypto markets, built around the
[Candle Range Theory](docs/notes/crt.md) framework (Timon / ICT University).

This repo is in heavy development. The current focus is:

1. Ingest MEXC perpetual futures market data (REST polling first, WebSocket next).
2. Detect all 5 CRT subtypes via a generic state machine.
3. Project DOL ladders (LHF → Initial DOL → Extended DOL) for each signal.
4. Paper-trade the signals to validate edge before going live.
5. Surface everything in a Rich TUI dashboard.

## Layout

```
src/crt/
├── data/        # MEXC client (REST + WS)
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
crt --symbols BTC_USDT ETH_USDT --tf 15m 1h 4h
```

## Tests

```bash
pytest -q
```
