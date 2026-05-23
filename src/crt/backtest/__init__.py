"""Historical replay engine for CRT setups."""

from crt.backtest.engine import BacktestReport, BacktestRunner
from crt.backtest.parallel import (
    ParallelBacktestReport,
    format_parallel_report,
    parallel_backtest,
)

__all__ = [
    "BacktestReport",
    "BacktestRunner",
    "ParallelBacktestReport",
    "parallel_backtest",
    "format_parallel_report",
]
