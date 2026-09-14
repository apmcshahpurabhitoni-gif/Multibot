# What's New — MULTIBOT2 v3.2.5

Generated from the single canonical source: release_notes.py.

- 🎨 Shared ponytail UI system now keeps Home, Signals, History, Calendar and Tools visually consistent.
- 📈 Home and Backtest use real equity curves for account and strategy performance instead of misleading bar summaries.
- 🧪 Backtest results are separated into overview, equity curve, performance, completed trades and detected opportunities.
- 🛡️ Backtest ratios are numerically bounded and non-finite metric values are safely handled before reaching the UI.
- 📋 Completed backtest trades now expose timestamp, side, entry, exit, P/L and bars held as real backend data.
- 🗂️ Signals and History date groups use consistent spacing and borders so headings and dates are never hidden or clipped.
- 📱 Mobile navigation and page cards were reduced for less visual clutter while preserving the five existing destinations.
- 💾 Production market-data cache now verifies Supabase health and reuses persistent Yahoo candles across restarts.
- 📡 Yahoo rate-limit backoff is isolated per symbol and cached data is reused during backoff when available.
- 🧹 Runtime artifacts such as __pycache__, .pyc files and local state databases are excluded from merge history.
- 📚 Release information now has one canonical source shared by Dashboard, Telegram and generated repository documentation.
