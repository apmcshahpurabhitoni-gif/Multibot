# MULTIBOT2 Production Incident Notes

## 2026-10-06 — Repeated sweep_v2 market-data errors

### Observed
Telegram is repeatedly receiving `ERROR — SCAN sweep_v2` with `MARKET_DATA_ERROR: OHLC data contains invalid values`. The screenshots show the same error recurring across multiple scan times. Paper mode remains active.

### Current audit finding

This is two separate issues and both must be tracked:

1. **Market-data validation failure**
   - `market_data.normalize_candles()` raises `MarketDataError("OHLC data contains invalid values")` when any required OHLC value becomes NaN after numeric coercion.
   - `sweep_v2` receives 1h data for NSE assets and 30m data for global assets, then canonicalizes/validates candles through the sweep candle-building path.
   - Root cause still needs to be isolated to the affected Yahoo symbol(s) and raw response/cached data. Do not weaken OHLC validation merely to suppress the error.

2. **Repeated Telegram error notification**
   - The current v3.5.0 release notes claim `MARKET_DATA_ERROR` evaluations stay silent.
   - Signal-level `MARKET_DATA_ERROR` is included in `NotificationService._silent_reasons`.
   - However, the screenshot is a **scan-level** message: `ERROR — SCAN sweep_v2`.
   - `main._notify_scan()` sends this scan error with `audit=False`.
   - Because scan events have no `signal_events` row, the signal silence gate is intentionally bypassed for scan notifications.
   - Therefore the current silence rule does **not** suppress repeated scan-level `MARKET_DATA_ERROR` messages.

### Required resolution

- Identify the exact affected symbol(s), Yahoo response, interval and candle containing invalid OHLC data.
- Preserve strict OHLC validation.
- Make scan-level market-data failures non-spammy: record them in scan history/dashboard/logs, but do not repeatedly send the same `MARKET_DATA_ERROR` scan notification on every scheduled cycle.
- Add regression tests proving repeated `sweep_v2` market-data failures do not generate repeated Telegram ERROR messages.
- Reconcile the v3.5.0 release note with the actual scan-level notification behavior.

### Constraint

Do not change trading strategy logic, risk rules, paper-only mode, or the locked market-data provider as a workaround for this incident.
