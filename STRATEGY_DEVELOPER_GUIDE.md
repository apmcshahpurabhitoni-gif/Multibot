# 🧩 MULTIBOT2 Strategy Developer Guide

## Goal

A strategy must be a **plug-in**, not a new application embedded inside `main.py`.

### Required outcome

A new strategy should normally require only:

```text
strategies/<strategy_id>/
├── __init__.py
├── strategy.py
├── manifest.yaml
└── tests/
```

The core runtime discovers it automatically.

---

## 1. Stable contract

Implement `strategies.base.Strategy`.

The plug-in must expose:

- `manifest`
- `generate_signal()`
- optional `data_request()`
- optional `prepare_candles()`
- optional `build_trade_plan()`
- optional `trailing_policy()`
- optional `backtest_signal()`
- `create_strategy()` factory

The canonical signal is `strategies.base.Signal`.

A directional signal must provide valid initial SL and TP through either the signal or the strategy's trade-plan implementation.

---

## 2. Manifest

The manifest declares the strategy's operational contract:

```text
id
name
version
description
assets
timeframes
schedule
account
parameters
capabilities
```

Parameters should declare their type, default and validation boundaries.

Do not expose a setting that can bypass a core safety rule.

---

## 3. Data boundary

The strategy tells the core which Yahoo interval and lookback it needs.

Examples:

```text
Trend Pulse → 1D
Sweep 4H       → 1H NSE / 30m global raw data
```

The provider remains Yahoo Finance.

The strategy must not create a second market-data transport.

---

## 4. Signal boundary

The strategy answers one question:

> “Given these completed candles, is there BUY, SELL, NEUTRAL or NO_SIGNAL?”

It may calculate indicators and strategy-specific exits.

It must not:

- send Telegram messages
- write directly to Supabase
- mutate account balances
- bypass duplicate checks
- bypass freshness
- place broker orders
- calculate dashboard presentation

---

## 5. Core lifecycle

The generic service owns:

```text
signal
 ↓
completion
 ↓
freshness
 ↓
duplicate
 ↓
account limit
 ↓
risk sizing
 ↓
trade plan
 ↓
persistence
 ↓
Telegram
```

This must remain strategy-independent.

---

## 6. Adding a strategy

### Step 1

Copy:

```text
strategies/_template/
```

to:

```text
strategies/my_strategy/
```

### Step 2

Give it a stable ID:

```text
my_strategy
```

### Step 3

Implement the strategy logic.

### Step 4

Declare its data/timeframe/assets in the manifest/manifest object.

### Step 5

Add deterministic unit tests.

### Step 6

Run:

```bash
python -m compileall -q .
pytest
```

### Step 7

Start MULTIBOT2.

The registry should discover the strategy automatically.

---

## 7. What must NOT be changed

Do not modify core safety logic merely to accommodate a strategy:

```text
Yahoo-only provider
paper-only mode
₹100,000 account
₹2,000 maximum base risk
1× leverage
1-hour freshness
maximum 2 sends / signal identity
account limits
Supabase authority
SQLite fallback
```

If a new strategy genuinely requires a new capability, add a **generic interface**, not a strategy-specific branch in `main.py`.

---

## 8. Dashboard configuration

The manifest is designed to become the source for Strategy Manager controls.

A parameter may be:

```text
editable
read-only
strategy-defined
system-controlled
```

The dashboard may expose strategy settings but must validate them against the strategy contract.

The dashboard must never be the authority for:

- risk enforcement
- freshness
- duplicate protection
- trade execution
- signal calculation

---

## 9. Versioning

Increment the strategy version when signal behavior changes.

Examples:

```text
1.0.0 → bug fix / implementation correction policy
1.1.0 → backward-compatible strategy parameter/behavior addition
2.0.0 → materially different signal model
```

Persist the version and parameter snapshot with generated signals/trades/backtests.

---

## 10. Backtesting

A supported strategy should use the same signal implementation as live evaluation wherever possible.

The backtest engine calculates common metrics:

```text
Return
Max Drawdown
Sharpe
Sortino
Win Rate
Profit Factor
Number of Trades
Average Trade
Maximum Losing Streak
Exposure
Risk-Adjusted Performance
```

Then the common rating engine produces:

```text
0–100 score
rating label
category breakdown
```

Never optimize parameters solely until a backtest looks attractive. Record the complete parameter snapshot and test period.
