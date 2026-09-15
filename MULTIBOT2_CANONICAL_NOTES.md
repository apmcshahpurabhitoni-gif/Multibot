# MULTIBOT2 Canonical Notes — v3.2.0

## Core

- Paper trading only.
- Yahoo Finance only.
- Asia/Kolkata timezone.
- ₹100,000 starting account.
- ₹2,000 maximum risk per trade.
- 1× leverage.
- Exactly 25 live assets.
- Supabase authoritative; SQLite fallback.
- Signal freshness exactly 1 hour.
- Maximum two Telegram sends per signal identity.

## Live universe

### NSE stocks

- RELIANCE
- BHARTIARTL
- HDFCBANK
- ICICIBANK
- SBIN
- TCS
- BAJFINANCE
- LT
- LICI
- SUNPHARMA
- HINDUNILVR
- INFY
- TITAN
- MARUTI
- KOTAKBANK

### Indices

- ^NSEI
- ^NSEBANK

### Global

- GC=F — Gold (XAU/USD)
- BTC-USD — Bitcoin (BTC)

### Forex

- EURUSD=X — EUR/USD
- GBPUSD=X — GBP/USD
- AUDUSD=X — AUD/USD
- USDJPY=X — USD/JPY
- NZDUSD=X — NZD/USD
- EURJPY=X — EUR/JPY

All six Forex pairs are 4H Sweep assets and use the canonical global 4H schedule: 02:30, 06:30, 10:30, 14:30, 18:30, 22:30 IST.

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
- Uses the full 25-asset live universe.
- Canonical schedules remain unchanged; Forex follows the Gold/global 4H schedule.

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
