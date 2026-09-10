# MULTIBOT2 Canonical Notes — v3.2.0

## Core

- Paper trading only.
- Yahoo Finance only.
- Asia/Kolkata timezone.
- ₹100,000 starting account.
- ₹2,000 maximum risk per trade.
- 1× leverage.
- Exactly 19 live assets.
- Supabase authoritative; SQLite fallback.
- Signal freshness exactly 1 hour.
- Maximum two Telegram sends per signal identity.

## Strategies

### Adaptive Trend Momentum

- ID: `adaptive_trend`
- Version: `1.0.0`
- BTC-USD + GC=F only.
- 1D candles.
- EMA 20/50, 40-day momentum, 20-day Donchian, ATR 14, volatility filter.
- ATR 1.5 initial stop, 2R target, optional ATR trailing.

### Sweep V2

- ID: `sweep_v2`
- Version: `2.0.0`
- Strict two-sided sweep + final-close classification.
- BUY / SELL / NEUTRAL.
- Market entry, sweep extreme SL, 1:2 TP.
- Canonical schedules remain unchanged.

## Plug-in architecture

`strategies/base.py` defines the contract; `strategies/registry.py` automatically discovers strategy packages.

Core lifecycle is strategy-independent.

## Backtesting

Required metrics:

- Return
- Max Drawdown
- Sharpe
- Sortino
- Win Rate
- Profit Factor
- Number of Trades
- Average Trade
- Maximum Losing Streak
- Exposure
- Risk-Adjusted Performance

Rating: 0–100, with Performance/Risk/Consistency/Efficiency/Robustness categories.

## Documentation

- `README.md` — human-facing project overview.
- `AI_REBUILD_SPEC.md` — complete reconstruction contract.
- `STRATEGY_DEVELOPER_GUIDE.md` — plug-in development instructions.
- `FINALIZATION_RULEBOOK.md` — release/regression guardrails.
