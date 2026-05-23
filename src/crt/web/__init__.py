"""FastAPI-based live dashboard.

A browser-facing alternative to the Rich TUI: serves an auto-refreshing
HTML page with the same watchlist + signals + positions panels, plus a
live Plotly chart for the focused symbol.
"""

from crt.web.app import WebDashboard, create_app

__all__ = ["WebDashboard", "create_app"]
