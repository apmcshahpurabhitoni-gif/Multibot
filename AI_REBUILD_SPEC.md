# 🤖 MULTIBOT2 — AI REBUILD SPECIFICATION

> **Purpose:** This is the canonical technical reconstruction document for MULTIBOT2. Give this file to another AI/developer when you need the system understood or recreated without explaining the project manually.

## 0. Reconstruction rule

Do not infer missing behavior from generic trading knowledge when this specification defines it.

The project is a **paper-trading multi-strategy engine**. Preserve the locked rules and interfaces below.

---

# 1. Identity

```text
Project: MULTIBOT2
Version: 3.3.0
Mode: PAPER ONLY
Market data: Yahoo Finance ONLY
Timezone: Asia/Kolkata
Starting account: ₹100,000
Base risk per trade: ₹2,000
Leverage: 1.0x
Freshness: exactly 1 hour
Persistence: Supabase authoritative + SQLite fallback
```

Canonical dashboard URL:

```text
https://multibot2-t74l.onrender.com/dashboard
```

---

# 2. Locked universe

Exactly 19 assets:

```text
RELIANCE
BHARTIARTL
HDFCBANK
ICICIBANK
SBIN
TCS
BAJFINANCE
LT
LICI
SUNPHARMA
HINDUNILVR
INFY
TITAN
MARUTI
KOTAKBANK
^NSEI
^NSEBANK
GC=F
BTC-USD
```

Yahoo mappings:

```text
NSE stock SYMBOL → SYMBOL.NS
^NSEI → ^NSEI
^NSEBANK → ^NSEBANK
GC=F → GC=F
BTC-USD → BTC-USD
```

Do not expand the live universe without an explicit project decision.

---

# 3. Accounts

Four independent account buckets exist:

```text
macro       limit 20
nifty       limit 5
ny_session  limit 3
sweep_4h    limit 3
```

Risk is ₹2,000 per trade and leverage is 1x.

A strategy declares which account it uses. The core account/risk engine remains authoritative.

---

# 4. Signal identity and messaging

Signal identity is:

```text
strategy + symbol + direction + candle timestamp
```

Maximum sends for one identity:

```text
send 1 = initial
send 2 = one reminder
send 3 = blocked
```

A scan must not consume a duplicate allowance until a signal has passed acceptance and is sent/persisted.

No directional signal means:

```text
no trade
no Telegram signal
```

Freshness:

```text
age <= 1 hour → FRESH
age > 1 hour → STALE
future timestamp → invalid
```

---

# 5. Core architecture

The architecture is deliberately split into core infrastructure and strategy plug-ins.

```text
market data
   ↓
candle normalization
   ↓
strategy loader / registry
   ↓
strategy engine
   ↓
canonical Signal
   ↓
completion
   ↓
freshness
   ↓
duplicate gate
   ↓
account/risk
   ↓
TradePlan
   ↓
persistence
   ↓
Telegram / dashboard
```

The core must not contain strategy-specific `if strategy == ...` branches for normal operation.

---

# 6. Strategy plug-in architecture

Directory model:

```text
strategies/
├── base.py
├── registry.py
├── _template/
├── adaptive_trend/
└── sweep_v2/
```

Each strategy package can contain:

```text
__init__.py
strategy.py
manifest.yaml
 tests/
```

The registry automatically discovers packages under `strategies/`.

The package exposes:

```python
create_strategy()
```

The returned object implements `Strategy`.

---

# 7. Strategy interface

`StrategyManifest` contains:

```text
id
name
version
description
assets
timeframes
schedule
parameters
capabilities
account
```

`Strategy` supports:

```text
generate_signal(symbol, candles, now)
data_request(symbol, period)
prepare_candles(symbol, candles, now)
build_trade_plan(signal, entry)
trailing_policy(config)
backtest_signal(symbol, candles, now)
validate_config(config)
```

Not every strategy needs to override every method.

---

# 8. Canonical Signal

A Signal contains:

```text
strategy
version
symbol
direction
timestamp
timeframe
reason
entry
stop_loss
take_profit
metadata
```

Directional values are:

```text
BUY
SELL
```

Non-directional values may include:

```text
NEUTRAL
NO_SIGNAL
```

`Signal.is_directional` is true only for BUY/SELL.

---

# 9. TradePlan

TradePlan contains:

```text
strategy
side
signal_timestamp
entry
stop_loss
take_profit
timeframe
strategy_version
metadata
trailing_policy
```

The generic risk engine calculates quantity from:

```text
risk / abs(entry - stop)
```

subject to the locked ₹2,000 maximum risk.

---

# 10. Adaptive Trend Momentum

Stable ID:

```text
adaptive_trend
```

Version:

```text
1.0.0
```

Assets:

```text
BTC-USD
GC=F
```

Timeframe:

```text
1D
```

Data request uses Yahoo daily candles with sufficient history.

Indicators:

```text
EMA fast = 20
EMA slow = 50
momentum = 40-day
Donchian = 20-day
ATR = 14
```

Volatility filter:

```text
ATR / close * 100
```

Default minimum volatility filter:

```text
0.5%
```

Signal model:

```text
LONG:
EMA20 > EMA50
AND 40-day momentum > 0
AND close > previous 20-day Donchian high
AND volatility filter passes

SHORT:
EMA20 < EMA50
AND 40-day momentum < 0
AND close < previous 20-day Donchian low
AND volatility filter passes
```

Otherwise:

```text
NO_SIGNAL
```

Default initial exits:

```text
stop distance = ATR14 × 1.5
reward/risk = 2.0
```

Default trailing policy:

```text
enabled = true
method = ATR
ATR multiple = 1.5
```

The strategy's parameter set is exposed through its manifest. Core risk/freshness rules cannot be bypassed by those parameters.

---

# 11. Sweep V2

Stable ID:

```text
sweep_v2
```

Version:

```text
2.0.0
```

Universe:

```text
all 19 live assets
```

Core rule:

```text
current high > previous high
AND
current low < previous low
```

Then classify by final close:

```text
close > previous high → BUY
close < previous low  → SELL
otherwise              → NEUTRAL
```

No two-sided sweep:

```text
NO_SIGNAL
```

Trade plan:

```text
BUY:
entry = market entry
SL = sweep/current low
TP = entry + 2 × (entry - SL)

SELL:
entry = market entry
SL = sweep/current high
TP = entry - 2 × (SL - entry)
```

Schedules:

```text
BTC: 01:30, 05:30, 09:30, 13:30, 17:30, 21:30 IST
Gold: 02:30, 06:30, 10:30, 14:30, 18:30, 22:30 IST
NIFTY/BANK: 09:15, 10:15, 11:15, 12:15, 13:15, 14:15 IST
NSE stocks: 09:15–13:15 and 13:15–15:15
```

NIFTY/BANK Sweep timeframe is 1H.

NSE stocks, Gold and BTC Sweep timeframe is 4H.

There is no pending-sweep persistence workflow.

---

# 12. Market data

Yahoo Finance is the only provider.

The provider is responsible for downloading data.

Strategies declare their required interval.

Do not create strategy-specific provider clients.

Yahoo 1-minute history is limited; long lookbacks must not request unsupported 1-minute history.

---

# 13. Candle requirements

Candle processing must distinguish raw provider data from canonical strategy candles.

NSE session candles must not manufacture a `15:15 → 16:15` bar.

Incomplete candles must never be treated as completed strategy candles.

A higher timeframe must only use completed constituent data.

---

# 14. Risk and account lifecycle

Core risk rules are not plug-ins.

The risk engine validates:

```text
account size = ₹100,000
risk <= ₹2,000
leverage = 1x
account daily limit
positive entry/SL
non-zero risk distance
```

Position quantity:

```text
₹2,000 / absolute(entry - stop)
```

A strategy may determine where its stop is, but it cannot override the maximum risk.

---

# 15. Persistence

SQLite tables:

```text
accounts
trades
signals
```

Supabase is authoritative when configured.

SQLite is local fallback/cache.

Signal metadata should preserve strategy version and parameter snapshot.

Trade payloads should preserve strategy version, timeframe and trailing policy when available.

---

# 16. Telegram

Telegram is an adapter.

It receives canonical signal/trade data.

It must not calculate strategy indicators or risk.

Commands include operational controls such as:

```text
/start
/menu
/check
/scan
/balance
/summary
/risk
/stats
/weekly
/newspause
/refreshnews
/backtest
/test
```

Incoming commands are accepted only from the configured Telegram chat ID.

Polling uses webhook deletion + `getUpdates` and handles polling conflicts without crashing the process.

---

# 17. Dashboard backend contract

The dashboard backend is presentation data only.

The API should expose:

```text
system
rules
universe
strategies
accounts
signals
trades
scan
health
counts
whats_new
version
```

Strategy catalog data includes:

```text
id
name
version
description
assets
timeframes
schedule
account
capabilities
parameters
```

This catalog is what enables the future Strategy Manager UI to build controls dynamically.

The frontend must not become the authority for signal/risk/trading logic.

---

# 18. Strategy configuration model

Strategy parameters are declared by the strategy manifest.

A parameter should contain enough information for a future dashboard to render a control:

```text
type
default
min
max
options
editable
```

System-controlled settings remain protected.

A future dashboard may allow a user to change strategy parameters such as:

```text
timeframe (only if strategy permits it)
indicator periods
SL method
TP method
trailing on/off
trailing multiple
risk within system limits
```

The dashboard must send configuration to the backend; the strategy validates it. Never trust raw frontend configuration.

---

# 19. Backtesting

Backtesting must be registry-driven.

There should be no strategy-specific dispatch chain in `main.py`.

A generic request is:

```text
strategy ID
symbol
period
optional validated parameters
```

The engine obtains data through the strategy's data request and evaluates the same strategy contract used by live evaluation where practical.

Required metrics:

```text
return
max drawdown
Sharpe
Sortino
win rate
profit factor
number of trades
average trade
maximum losing streak
exposure
risk-adjusted performance
```

---

# 20. Rating system

Rating is 0–100.

Categories:

```text
Performance  25%
Risk         25%
Consistency  20%
Efficiency   15%
Robustness   15%
```

Labels:

```text
90–100 Exceptional
80–89  Strong
70–79  Good
60–69  Moderate
50–59  Weak
<50    Poor
```

The score is a decision-support metric, not a forecast.

Sample size reduces confidence so a tiny number of trades cannot dominate the rating automatically.

---

# 21. Experiment reproducibility

A backtest result must preserve:

```text
strategy ID
strategy version
symbol
timeframe
parameters
period
starting capital
risk assumptions
all required metrics
rating
rating breakdown
```

This is necessary to explain old results after strategy parameters change.

---

# 22. Error behavior

General rules:

```text
missing data → no signal / explicit error state
future signal timestamp → reject
stale directional signal → do not dispatch
invalid SL distance → reject safely
duplicate send count >= 2 → block
account limit reached → block
Telegram failure → do not silently claim success
provider failure → record runtime error; do not fabricate data
```

No component should fabricate market data.

---

# 23. Startup/deployment

Render has one web service.

Build:

```text
pip install -e .
```

Start:

```text
python startup.py && python main.py
```

Health:

```text
/ping
```

Required environment variables include:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
SUPABASE_URL
SUPABASE_KEY
WEBHOOK_URL
DASHBOARD_URL
```

Only values actually consumed by runtime should be treated as functional configuration.

---

# 24. Testing requirements

Before release:

```bash
python -m compileall -q .
pytest
```

Tests must cover at least:

```text
configuration
19-asset universe
strategy registry
strategy contract
Adaptive Trend
Sweep V2
signal freshness
signal identity
2-send limit
risk/account limits
backtesting metrics
Telegram formatting
DB persistence
market/candle behavior
main runtime imports
```

Most important architectural regression test:

> A strategy can be discovered and evaluated through the registry without adding a strategy-specific branch to the core runtime.

---

# 25. Files and responsibilities

Complete inventory. A rebuild that omits any line here will lose behavior that
no other section describes.

```text
# --- runtime ---------------------------------------------------------------
main.py
    Runtime orchestration, HTTP endpoints, Telegram command loop.
startup.py
    Startup sequencing and keepalive bootstrap.

# --- locked configuration --------------------------------------------------
config.py
    Locked global rules and asset configuration.
release_notes.py
    APP_VERSION, release highlights, Telegram /whatsnew source.
bot_settings.py
    Server-side persistence and validation for the operator-editable
    configuration: accounts (capital, daily trade limit, risk per trade),
    extra assets plugged into existing account groups, and account routing.

# --- strategy execution ----------------------------------------------------
strategy_engine.py
    Data request + strategy evaluation boundary.
strategy_service.py
    Shared signal-to-trade lifecycle.
strategy_scheduler.py
    Per-strategy scheduling and completed-candle timing.

# --- signal control --------------------------------------------------------
signal_gate.py
    Freshness and duplicate identity controls.
signal_lifecycle.py
    Pipeline status transitions (RECORDED -> SENT -> EXPIRED).
notification_service.py
    Telegram/webhook delivery with send accounting.

# --- market data -----------------------------------------------------------
market_data.py
    Canonical market data handling.
candles.py
    Candle frame construction and completion rules.
yahoo_provider.py
    Yahoo transport and durable cache.

# --- trading and research --------------------------------------------------
trading.py
    Generic account/risk/trade primitives.
backtest.py
    Generic backtesting + metrics + rating.
sweep_engine.py
    Sweep calculations.

# --- persistence -----------------------------------------------------------
db.py
    Supabase/SQLite persistence.
schema.sql
    Canonical Supabase DDL (authoritative).
supabase/schema.sql
    Byte-mirrored copy of schema.sql; parity enforced by tests/test_schema_parity.py.

# --- news and calendar -----------------------------------------------------
news.py
    Economic calendar fetch and parsing.
news_gate.py
    News-pause gating decisions.
calendar_store.py
    Persisted calendar events.
reminders.py
    Follow-up reminder scheduling.
trade_monitor.py
    Open-trade supervision and exits.

# --- delivery --------------------------------------------------------------
telegram.py
    Telegram rendering and transport.
dashboard.py
    Dashboard-safe backend payloads only.

# --- strategy plug-ins -----------------------------------------------------
strategies/base.py
    Stable Strategy, Manifest, Signal contracts.
strategies/registry.py
    Automatic discovery. discover_strategies() is the only entry point.
strategies/_template/
    Scaffold for a new strategy. Copy, rename, edit.
strategies/adaptive_trend/
    Trend Pulse strategy only.
strategies/engulfing_66_sma/
    Engulf 66 SMA strategy only.
strategies/sweep_v2/
    Sweep 4H strategy only.

# --- dashboard -------------------------------------------------------------
dashboard.html
    Single-page semantic structure. Five pages.
app.js
    Dashboard UI rendering and interaction.
appearance.js
    Theme/style/accent state and persistence.
dashboard-live-wiring.js
    Read-only presentation bridge over fetched snapshots.
styles.css
    Component and page layout.
foundation.css
    Canonical geometry and structure tokens.
appearance-overrides.css
    Theme appearance layer.

# --- delivery of the build -------------------------------------------------
pyproject.toml
    Version, dependency pins, py-modules inventory.
render.yaml
    Deployment, env-var contract, health path.
tests/
    Contract regression suite.
tools/check_release_docs.py
    Version/document consistency gate.
.github/workflows/tests.yml
    CI: Python 3.12, editable install, compileall, import discovery, pytest.
```

24 root modules, 3 registered strategies, 7 dashboard assets. This list is
enforced by tests/test_rebuild_spec_inventory.py.

---

# 26. What must never happen in a rebuild

Do NOT:

```text
❌ restore TrendPulse as a second parallel runtime
❌ add strategy-specific branches to main.py
❌ create one service class per strategy with duplicated lifecycle logic
❌ make dashboard JavaScript calculate trading decisions
❌ let dashboard bypass risk/freshness/duplicate controls
❌ make strategy code write directly to DB
❌ let strategies send Telegram directly
❌ make timeframe a global single value
❌ silently change paper trading to live trading
❌ expand the asset universe without authorization
❌ invent market data when Yahoo fails
```

If a new capability is required, extend the generic interface first.

---

# 27. Reconstruction sequence

An AI recreating the repository should implement in this order:

```text
1. config + locked universe
2. market data + candles
3. Signal + TradePlan contracts
4. risk/account primitives
5. signal gate
6. strategy base + registry
7. Adaptive Trend plugin
8. Sweep V2 plugin
9. strategy engine
10. generic strategy service
11. persistence
12. Telegram adapter
13. backtest + metrics + rating
14. dashboard backend payload
15. main runtime
16. tests
17. documentation
18. compile + pytest + integration audit
```

The final result must preserve the separation:

```text
STRATEGY = decides
CORE = validates / sizes / persists / dispatches
DASHBOARD = presents / configures through validated backend APIs
```

---

# 28. Definition of “plug-and-play complete”

The architecture is complete only when Strategy #3 can be added as a new strategy package and discovered automatically **without rewriting the core lifecycle**.

The core files should remain unchanged for ordinary new strategies:

```text
main.py
strategy_service.py
risk/account logic
signal_gate.py
telegram.py
db.py
dashboard.py
backtest.py
```

If one of those files needs a change for every new strategy, the architecture has regressed.

---

# 29. Current release

```text
MULTIBOT2 v3.3.0

🧩 Automatic strategy discovery
🧠 Trend Pulse (adaptive_trend)
🔎 Engulf 66 SMA and Sweep 4H unified under the strategy contract
📊 11 backtest metrics
⭐ 0–100 strategy rating
🧪 Reproducible versioned experiments
🤖 AI rebuild specification
📚 Strategy developer template
🛡️ Locked paper-trading safety rules
♿ WCAG AA contrast contract across every style/accent/theme combination
```

---

# 30. Registered strategy inventory

Three strategies are discovered by `strategies.registry.discover_strategies()`.
There is no `build_default_registry`; discovery is the only entry point. A
rebuild that ships fewer or more strategies is wrong.

```text
Trend Pulse 1.0.0
    id           adaptive_trend
    timeframes   1d
    assets       2
    account      macro
    schedule     completed_candle

Engulf 66 SMA 1.0.2
    id           engulfing_66_sma
    timeframes   1h
    assets       25 (LIVE_SYMBOLS)
    account      macro
    schedule     completed_candle
    parameters   sma_length 66, atr_length 14, zone_atr 0.35,
                 min_body_atr 0.45, max_body_atr 3.5, strict_engulf false,
                 min_slope_atr 0.15, slope_length 10, cooldown 12,
                 confirm_only true, stop_atr 1.2, target_r 2.0
    notes        validate_config() rejects max_body_atr < min_body_atr.
                 data_request() asks for 1h/60d. Signals are emitted only on
                 completed candles.

Sweep 4H 2.1.0
    id           sweep_v2
    timeframes   1h, 4h
    assets       25 (LIVE_SYMBOLS)
    account      sweep_4h
    schedule     completed_candle
```

This inventory is asserted against the live registry by
tests/test_version_consistency.py, so it cannot drift from the code.
