# 🤖 MULTIBOT2

> ### 🧠 A modular, plug-and-play algorithmic **paper-trading engine**
>
> **Yahoo Finance · Multi-Strategy · Risk Controlled · Telegram · Supabase · Dashboard · Strategy Lab**

[![Version](https://img.shields.io/badge/version-3.1.0-111827?style=for-the-badge)](.)
[![Mode](https://img.shields.io/badge/mode-PAPER-16a34a?style=for-the-badge)](.)
[![Provider](https://img.shields.io/badge/data-Yahoo%20Finance-7c3aed?style=for-the-badge)](.)
[![Python](https://img.shields.io/badge/python-3.11%2B-2563eb?style=for-the-badge)](.)

---

## 🌟 What is MULTIBOT2?

MULTIBOT2 is a **paper-trading research and signal engine** designed around one idea:

> 🧩 **Strategies should be replaceable. Core trading safety should not be.**

The system scans a locked 19-asset universe using Yahoo Finance, evaluates independently discoverable strategy plug-ins, validates signals, applies freshness and duplicate controls, sizes trades using the locked risk model, persists state, sends Telegram notifications, and exposes operational data to the dashboard.

It is deliberately **paper only**. It does not place live broker orders.

---

## 🚀 What's new in v3.1.0?

### 🧩 Plug-and-play strategies

Strategies are now discovered automatically from `strategies/`. The core runtime does not need a new `if/elif` branch every time a strategy is added.

### 🧠 Adaptive Trend Momentum

TrendPulse has been retired. **Adaptive Trend Momentum** is now the BTC-USD + Gold strategy and uses daily candles with:

- 📈 EMA 20 / EMA 50 trend relationship
- 🏃 40-day momentum
- 🧱 20-day Donchian breakout
- 🌡️ ATR 14
- 🔎 volatility filter
- 🟢 LONG / 🔴 SHORT / ⚪ NO SIGNAL
- 🛑 ATR-based initial stop
- 🎯 fixed reward/risk target
- 🪢 optional ATR trailing-stop policy

### 🔎 Sweep V2 preserved

Sweep V2 remains available under the same strategy contract and retains its strict two-sided sweep + final-close classification model and canonical schedules.

### 📊 Strategy Lab foundation

Backtesting now exposes:

**Return · Max Drawdown · Sharpe · Sortino · Win Rate · Profit Factor · Number of Trades · Average Trade · Losing Streak · Exposure · Risk-Adjusted Performance**

and a transparent **0–100 Strategy Rating**.

### ⭐ Versioned experiments

Backtest results and signal metadata carry strategy version and parameter snapshots so historical decisions remain explainable.

### 🤖 AI reconstruction documentation

`AI_REBUILD_SPEC.md` describes the architecture, contracts, locked rules, data flow, failure behavior and implementation requirements in enough detail for another AI/developer to reconstruct the project.

---

## 🧭 Architecture at a glance

```text
                    ┌──────────────────────┐
                    │      Dashboard       │
                    │ Strategy Manager/Lab │
                    └──────────┬───────────┘
                               │
                        configuration
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Strategy Registry   │
                    │  automatic discovery │
                    └──────────┬───────────┘
                               │
                  ┌────────────┴────────────┐
                  ▼                         ▼
          Adaptive Trend                Sweep V2
                  │                         │
                  └────────────┬────────────┘
                               ▼
                         Canonical Signal
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Generic Pipeline   │
                    ├──────────────────────┤
                    │ completion           │
                    │ freshness            │
                    │ duplicate gate       │
                    │ account/risk         │
                    │ trade plan            │
                    │ persistence           │
                    │ Telegram              │
                    │ dashboard             │
                    └──────────┬───────────┘
                               ▼
                     🗄️ Supabase / SQLite
```

---

## 🧩 Plug-and-play: add a new strategy

Create a folder:

```text
strategies/my_strategy/
├── __init__.py
├── strategy.py
├── manifest.yaml
└── tests/
```

Implement the stable `Strategy` contract and expose `create_strategy()`.

The loader automatically discovers strategy packages at startup.

### The goal

Adding Strategy #3 should **not** require changing:

- ❌ `main.py`
- ❌ Telegram transport
- ❌ Dashboard data layer
- ❌ Database layer
- ❌ duplicate gate
- ❌ freshness rules
- ❌ core risk engine
- ❌ scheduler core

The new strategy declares its own:

- assets
- timeframes
- data requirements
- schedule
- parameters
- capabilities
- account
- signal logic
- initial exit policy
- trailing policy
- backtest support

See `STRATEGY_DEVELOPER_GUIDE.md` for the exact workflow.

---

## 📦 Built-in strategies

| Strategy | Assets | Timeframe | Main job |
|---|---|---|---|
| 🧠 Adaptive Trend Momentum | BTC-USD, GC=F | 1D | Trend + momentum + breakout |
| 🔎 Sweep V2 | 19-asset universe | Asset/schedule-defined | Liquidity sweep classification |

Strategies are identified by stable IDs such as `adaptive_trend` and `sweep_v2`, while human-readable names and versions are carried separately.

---

## 🛡️ Locked trading rules

| Rule | Value |
|---|---:|
| 💰 Starting account | ₹100,000 |
| 🎯 Base risk / trade | ₹2,000 |
| ⚙️ Leverage | 1× |
| 📡 Provider | Yahoo Finance only |
| 🧪 Trading mode | Paper only |
| ⏳ Signal freshness | exactly 1 hour |
| 🔁 Maximum sends / identity | 2 |
| 🌏 Timezone | Asia/Kolkata |
| 🗄️ Primary persistence | Supabase |
| 💾 Fallback | SQLite |

### Account limits

```text
macro       20
nifty        5
ny_session   3
sweep_4h    3
```

These are **core safety rules**. Strategy configuration cannot bypass them.

---

## 🔁 Signal lifecycle

Every strategy follows the same safety path:

```text
📡 Yahoo data
      ↓
✅ validation
      ↓
🕯️ canonical candles
      ↓
🧠 strategy plug-in
      ↓
📨 canonical Signal
      ↓
⏱️ completion check
      ↓
⏳ freshness ≤ 1h
      ↓
🔁 duplicate identity check
      ↓
🛡️ account + risk validation
      ↓
📐 TradePlan
      ↓
💾 Supabase / SQLite
      ↓
💬 Telegram
      ↓
📊 Dashboard
```

No directional signal means **no trade and no Telegram signal dispatch**.

---

## 🔐 Signal identity

A signal identity is:

```text
strategy + symbol + direction + candle timestamp
```

Maximum Telegram sends for one identity:

```text
1️⃣ Initial
2️⃣ One reminder
🚫 Third send blocked
```

Scanning alone does not consume the send allowance.

---

## 📊 Strategy Lab & rating

Every supported backtest should expose the same analytical vocabulary.

### Metrics

- 💰 Return
- 📉 Maximum Drawdown
- 📈 Sharpe
- 🛡️ Sortino
- 🎯 Win Rate
- 💎 Profit Factor
- 🔢 Number of Trades
- 💵 Average Trade
- 🔥 Maximum Losing Streak
- 📡 Exposure
- ⚖️ Risk-Adjusted Performance

### ⭐ Rating

The Strategy Rating is a **0–100 decision-support score**, not a prediction.

```text
90–100  🟢 Exceptional
80–89   🟢 Strong
70–79   🟡 Good
60–69   🟠 Moderate
50–59   🟠 Weak
<50     🔴 Poor
```

The rating is broken into:

```text
Performance  25%
Risk         25%
Consistency  20%
Efficiency   15%
Robustness   15%
```

The robustness component also considers sample size and losing-streak behavior so a tiny number of lucky trades does not automatically dominate a larger sample.

---

## 🧪 Reproducible research

Backtests retain the identity of the experiment:

```text
strategy ID
strategy version
symbol
timeframe
parameter snapshot
start/end period
capital/risk assumptions
metrics
rating + breakdown
```

This lets you answer:

> “Which exact strategy version and parameters produced this result?”

---

## 🌐 Live universe

Exactly **19 live assets** are configured:

### 🇮🇳 NSE stocks

`RELIANCE · BHARTIARTL · HDFCBANK · ICICIBANK · SBIN · TCS · BAJFINANCE · LT · LICI · SUNPHARMA · HINDUNILVR · INFY · TITAN · MARUTI · KOTAKBANK`

### 📊 Indices

`^NSEI · ^NSEBANK`

### 🌍 Global

`GC=F · BTC-USD`

The universe is intentionally locked.

---

## 🔎 Sweep V2

Sweep V2 remains a separate plug-in, but it uses the same core lifecycle.

### Rules

- two-sided sweep required
- final-close classification
- BUY / SELL / NEUTRAL
- market entry
- sweep extreme stop
- 1:2 reward/risk target
- no pending-sweep persistence/workflow

### Canonical schedules

**Bitcoin:** 01:30 · 05:30 · 09:30 · 13:30 · 17:30 · 21:30 IST

**Gold:** 02:30 · 06:30 · 10:30 · 14:30 · 18:30 · 22:30 IST

**NIFTY / BANK NIFTY:** 09:15 · 10:15 · 11:15 · 12:15 · 13:15 · 14:15 IST

**NSE stocks:** 09:15–13:15 and 13:15–15:15 session segments

---

## 💬 Telegram

Telegram is an output/command adapter, not a strategy engine.

Messages receive their strategy name, version, symbol, timeframe, entry, SL, TP, risk and status from the canonical signal/trade model.

The bot also provides operational commands such as `/start`, `/check`, `/balance`, `/summary`, `/risk`, `/stats`, `/weekly`, `/backtest`, `/test`, `/newspause` and `/refreshnews`.

---

## 🗄️ Persistence

MULTIBOT2 uses:

```text
Supabase  → authoritative production persistence
SQLite    → local state/cache/fallback
```

Signal send history is persisted so duplicate protection can survive process restarts.

---

## 🏗️ Repository structure

```text
MULTIBOT2/
├── main.py                    # runtime orchestration
├── config.py                  # locked system configuration
├── strategy_engine.py          # strategy data/evaluation boundary
├── strategy_service.py         # shared signal lifecycle
├── backtest.py                 # registry-driven research engine
├── trading.py                  # account/risk/trade primitives
├── signal_gate.py              # freshness + duplicate controls
├── market_data.py              # canonical market data helpers
├── candles.py                  # candle normalization/building
├── yahoo_provider.py            # Yahoo-only provider
├── db.py                        # Supabase + SQLite persistence
├── telegram.py                  # Telegram adapter
├── dashboard.py                 # dashboard backend payloads
├── sweep_engine.py              # Sweep V2 calculations
│
├── strategies/
│   ├── base.py                 # stable plug-in contract
│   ├── registry.py              # automatic discovery
│   ├── _template/              # new-strategy starter
│   ├── adaptive_trend/          # Adaptive Trend Momentum
│   └── sweep_v2/                # Sweep V2 plug-in
│
├── tests/                       # canonical test suite
│
├── README.md                    # human-facing documentation
├── AI_REBUILD_SPEC.md           # complete AI reconstruction contract
├── STRATEGY_DEVELOPER_GUIDE.md  # how to create a plug-in
├── FINALIZATION_RULEBOOK.md     # release/regression rules
└── MULTIBOT2_CANONICAL_NOTES.md # compact canonical facts
```

---

## 🚀 Run

```bash
pip install -e ".[test]"
python startup.py
python main.py
```

Render uses:

```text
python startup.py && python main.py
```

Health endpoint:

```text
/ping
```

Dashboard:

```text
https://multibot2-t74l.onrender.com/dashboard
```

---

## 🧪 Validate before release

```bash
python -m compileall -q .
pytest
```

The CI pipeline also installs the package, compiles all Python modules, imports runtime modules, and runs the complete test suite.

---

## 🤖 Want another AI to understand the entire project?

Give it **`AI_REBUILD_SPEC.md` first**.

That document is intentionally much more detailed than this README and is the canonical reconstruction guide.

For strategy-only work, give it:

> `AI_REBUILD_SPEC.md` + `STRATEGY_DEVELOPER_GUIDE.md`

---

## 🧭 Project philosophy

```text
🧩 Modular strategies
🛡️ Immutable core safety rules
📊 Evidence before optimization
🔁 Reproducible experiments
💾 Durable state
💬 Clear notifications
🎨 Presentation separated from trading logic
```

**MULTIBOT2 v3.1.0 — built to add strategies without rebuilding the bot.** 🚀
