# What's New — MULTIBOT2 v3.2.6

Generated from the single canonical source: release_notes.py.

- 🎨 Final ponytail consistency pass aligns Home, Signals, History, Calendar and Tools around one shared panel and spacing system.
- 📱 Backtest trades and generated signals are bounded, touch-scrollable panels that no longer stretch the mobile page or sit behind navigation.
- 🧪 Backtest results are semantically separated into overview, equity curve, performance, completed trades and backtest signals.
- 🔒 Dashboard API reads now validate HTTP status, body and JSON before rendering, preventing stale results after empty or malformed responses.
- 🧭 Live signals now expose lifecycle state separately from actionability; incomplete historical records are diagnostic, never presented as actionable trades.
- 🧩 Canonical signal entry, stop and target levels are persisted with lifecycle events so runtime, dashboard and future consumers share the same facts.
- 🛡️ Backtest ratios are numerically bounded and non-finite metric values are safely handled before reaching the UI.
- 📋 Completed backtest trades now expose timestamp, side, entry, exit, P/L and bars held as real backend data.
- 🗂️ Signals and History date groups use consistent spacing and borders so headings and dates are never hidden or clipped.
- 📱 Mobile navigation and page cards were reduced for less visual clutter while preserving the five existing destinations.
- 💾 Production market-data cache now verifies Supabase health and reuses persistent Yahoo candles across restarts.
- 📡 Yahoo rate-limit backoff is isolated per symbol and cached data is reused during backoff when available.
- 🧹 Runtime artifacts such as __pycache__, .pyc files and local state databases are excluded from merge history.
- 📚 Release information now has one canonical source shared by Dashboard, Telegram and generated repository documentation.
