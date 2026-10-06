# What's New — MULTIBOT2 v3.5.0

Generated from release_notes.py.

- 🔇 Per-sweep scan noise is gone: the 🔎 Scan complete Telegram bubble is now strictly opt-in per channel, and stale, duplicate, reminder, account-limit and MARKET_DATA_ERROR evaluations stay silent while the dashboard and deliveries audit still record every evaluated signal.
- 🔐 Telegram chat ids are now secrets in the notifications card: the dashboard API redacts every channel target and secret, so a screenshot or API read can no longer expose your chat id.
- 🛟 The environment-default Telegram channel shows a Default chip instead of Remove, so the last working notification path cannot be deleted by accident, and editing it only changes the chat id.
- 📱 The notifications card was rebuilt into a compact three-line channel row with a scannable event grid, saving vertical space in Tools.
