# MULTIBOT2 Finalization Rulebook — v3.2.0

## 🔒 Locked rules

1. Paper trading only.
2. Yahoo Finance only.
3. Asia/Kolkata timezone.
4. Exactly 19 live assets.
5. ₹100,000 account.
6. ₹2,000 maximum risk per trade.
7. 1× leverage.
8. Account limits: macro 20, nifty 5, ny_session 3, sweep_4h 3.
9. Freshness: age ≤1h fresh; >1h stale; future invalid.
10. Signal identity: strategy + symbol + direction + candle timestamp.
11. Maximum two sends per identity: initial + one reminder.
12. No directional signal = no trade / signal dispatch.
13. Supabase authoritative, SQLite fallback.
14. Dashboard is presentation/configuration UI; backend remains authoritative.

## 🧩 Architecture rules

- Strategies are automatic plug-ins.
- New strategies belong under `strategies/`.
- Normal new strategies must not require changes to `main.py` or shared lifecycle modules.
- Strategy timeframes are strategy-owned.
- Strategy parameters are validated by the strategy/backend contract.
- Core safety rules cannot be overridden by dashboard configuration.
- Telegram, DB and dashboard do not implement strategy logic.
- Backtesting is registry-driven.

## 🧪 Release checks

```bash
python -m compileall -q .
pytest
```

Also search for:

```text
TrendPulse
strategy-specific branches in main.py
stale global timeframe assumptions
TODO/FIXME placeholders
orphan imports
obsolete tests
```

A release is not final if legacy strategy architecture remains active or if documentation contradicts runtime behavior.
