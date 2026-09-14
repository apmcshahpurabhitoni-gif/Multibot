# AI_CONTEXT.md — MULTIBOT2 Repository Understanding Guide

Purpose: this is the first document an AI or developer should read before changing MULTIBOT2.

## What the system is

MULTIBOT2 (Mavis) is a modular algorithmic paper-trading research and signal system.

It uses Yahoo Finance only, scans a locked 19-asset universe, discovers strategy plug-ins, produces canonical signals, enforces completion/freshness/duplicate/risk gates, manages paper trades, persists state, sends Telegram messages, serves a mobile dashboard and supports backtesting.

It does not place live broker orders.

## Read order

1. AI_CONTEXT.md
2. release_notes.py
3. config.py
4. main.py
5. strategy_service.py
6. trading.py, signal_gate.py and signal_lifecycle.py
7. backtest.py
8. dashboard.py, dashboard.html, app.js and styles.css
9. db.py, yahoo_provider.py and market_data.py
10. strategies/
11. tests/

## Locked invariants

- Paper mode only.
- Yahoo Finance is the market-data provider.
- Signal freshness is exactly 1 hour.
- Exactly 19 live assets.
- Starting account size is ₹100,000.
- Base risk per trade is ₹2,000.
- Leverage is 1x.
- Timezone is Asia/Kolkata.
- Signal identity is strategy + symbol + direction + candle timestamp.
- Maximum delivery count per identity is 2: initial plus one reminder.
- Strategy configuration cannot bypass core account limits.
- Strategies must use the shared lifecycle.

config.py validates many of these. Treat validation as a product contract.

## Architecture

Yahoo Finance
→ provider/cache
→ validation
→ canonical candles
→ strategy plug-in
→ canonical Signal
→ completion check
→ freshness check
→ duplicate/delivery gate
→ account and risk validation
→ TradePlan
→ persistence
→ Telegram
→ dashboard snapshot

No directional signal means no directional paper trade or Telegram dispatch.

main.py orchestrates runtime.
StrategyService owns shared scan/dispatch behavior.
TradeMonitor monitors paper trades.
StrategyScheduler controls scheduled execution.

## Strategies

The registry automatically discovers plug-ins under strategies/.

A strategy package provides a manifest, implementation, stable contract and create_strategy().

Adding a strategy should not require strategy-specific branches in main.py, Telegram, dashboard, database, duplicate gate or core risk logic.

Current built-ins:
- adaptive_trend: BTC-USD and Gold daily trend/momentum strategy.
- sweep_v2: locked 19-asset sweep classification strategy with asset-specific schedules.

## Market data and cache

Yahoo Finance is the only provider.

Cache behavior:
- cache-first where available;
- Supabase can provide remote production persistence;
- SQLite is fallback/local state;
- Yahoo backoff is isolated per symbol;
- recent cache can be reused during backoff;
- cache failure must not itself crash a strategy scan.

Production healthy examples:
Market data cache health | enabled=True remote=True reason=OK
Yahoo persistent cache hit
Yahoo request skipped during backoff ... source=cache

SUPABASE_NOT_CONFIGURED is expected on an intentionally unconfigured demo deployment and is not automatically a strategy failure.

## Persistence

Primary production persistence: Supabase.
Fallback/local state: SQLite.

Persisted state can include accounts, signals, delivery history, trades, scan runs, market-data cache and calendar cache.

Never commit __pycache__, pyc files, local databases, logs or secrets.

## Signals and trades

Canonical signals carry strategy identity/version, symbol, direction, timestamp, timeframe, reason, entry/SL/TP and metadata.

Only BUY and SELL are directional.

Delivery can be fresh, stale, duplicate-limited, reminder-pending, rejected by account/risk rules, sent or transport-failed.

Dashboard and Telegram consume canonical data. They must not duplicate strategy calculations.

## Dashboard and UI data contract

The dashboard has five destinations only: Home, Signals, History, Calendar and Tools.

Semantic ownership is locked:
- Signals = persisted runtime BUY/SELL lifecycle events.
- History = completed paper trades only.
- Backtest trades = simulated completed trades for the selected test only.
- Backtest signals = BUY/SELL signals generated during the selected test only.

Do not mix runtime and backtest arrays. Do not rename diagnostic lifecycle records as actionable opportunities.

Signal contract:
- strategy/version, symbol, direction, timestamp, timeframe and reason are identity/context.
- entry, stop_loss and take_profit are canonical levels.
- has_trade_levels and actionable are explicit presentation facts.
- freshness and pipeline_status describe lifecycle, not profitability.

Old historical rows may lack levels. Render them as diagnostic/non-actionable records; never display fake dashes as an actionable trade setup.

API readers must validate HTTP status, response body and JSON before rendering. Backtest failures must hide failed results instead of leaving stale results underneath.

Scrollable data panels are a shared UI primitive. Backtest trades/signals use bounded internal scrolling and mobile content always reserves bottom-navigation safe-area space.

## Backtesting

backtest.py is research infrastructure, not the live dispatcher.

Backtest UI order:
1. Overview: starting account, ending account, trades, return.
2. Equity curve: account value after completed trades.
3. Performance: return, drawdown, Sharpe, Sortino, win rate, profit factor, number of trades, average trade, losing streak, exposure, risk-adjusted performance and rating.
4. Completed trades: timestamp, side, entry, exit, P/L and bars held.
5. Detected opportunities.

Ratios must be numerically safe. Non-finite values must be handled before UI formatting. Metric text must never overflow cards.

Do not replace the equity curve with a bar chart unless the product contract changes.

## Dashboard

Backend payload: dashboard.py
HTTP/API serving: main.py
Frontend: dashboard.html, app.js, styles.css

Destinations:
- Home
- Signals
- History
- Calendar
- Tools

UI rules:
- preserve five destinations;
- keep mobile navigation compact;
- use shared page headers;
- reduce unnecessary large boxes;
- separate unrelated information;
- prevent text overflow;
- keep date headers inside containers;
- use real equity curves;
- do not invent fake data.

## Calendar

news.py provides cache-first economic-calendar behavior centered on Forex Factory data.

The UI reads cached data. Upstream should not be polled on every UI render. JSON is preferred, with XML/HTML fallbacks.

## Telegram

telegram.py is an adapter/message formatter. main.py handles commands.

Operational commands include /start, /menu, /check, /scan, /balance, /summary, /risk, /stats, /weekly, /backtest, /test, /newspause, /refreshnews and /whatsnew.

Telegram must consume canonical runtime data.

## Single source of truth for What's New

Canonical source: release_notes.py.

It owns:
- APP_VERSION
- RELEASE_HIGHLIGHTS
- Markdown rendering
- Telegram rendering

Consumers:
- config.py re-exports version/highlights for runtime compatibility.
- Dashboard snapshot sends canonical highlights.
- Telegram /whatsnew renders canonical highlights.
- WHATS_NEW.md mirrors the canonical release.
- README current release block must match canonical release.

When changing a release:
1. Edit release_notes.py.
2. Sync README and WHATS_NEW.md.
3. Run release consistency checks.
4. Verify Dashboard and Telegram show the same list.
5. Update AI_CONTEXT.md only if architecture changed.

Never maintain separate handwritten What's New lists.

## Documentation map

README.md: human overview and quick start.
AI_CONTEXT.md: current AI/developer orientation.
AI_REBUILD_SPEC.md: deeper reconstruction contract.
WHATS_NEW.md: current release mirror.
STRATEGY_DEVELOPER_GUIDE.md: plug-in authoring.
MULTIBOT2_CANONICAL_NOTES.md: compact canonical facts.
FINALIZATION_RULEBOOK.md: release/regression rules.
schema.sql: persistence/cache schema.
tests/: executable contracts.

If docs conflict with runtime, inspect tests and runtime code before changing behavior.

## Deployment and release checks

Render exposes /ping and the dashboard/API from main.py.

Before merge:
- compile Python;
- run tests;
- inspect production logs;
- ensure runtime artifacts are not tracked;
- ensure release docs match release_notes.py;
- inspect all five dashboard pages on mobile after UI changes.

## Repository map

main.py: runtime orchestration, HTTP and Telegram commands
config.py: locked configuration and compatibility exports
release_notes.py: single release/What's New source
strategy_service.py: shared strategy lifecycle
strategy_engine.py: strategy evaluation boundary
strategies/: plug-in registry and implementations
trading.py: account/trade primitives
trade_monitor.py: paper trade monitoring
signal_gate.py: freshness/duplicate gate
signal_lifecycle.py: canonical lifecycle formatting
backtest.py: research and metrics
dashboard.py: dashboard payload
dashboard.html: dashboard shell
app.js: frontend rendering
styles.css: shared UI system
yahoo_provider.py: Yahoo provider/cache integration
market_data.py: market-data helpers
db.py: Supabase/SQLite persistence
telegram.py: Telegram adapter/messages
news.py: economic calendar service
calendar_store.py: durable calendar cache
schema.sql: persistence schema
tests/: regression contracts

## Final AI instruction

Do not infer the whole architecture from one file.

Before editing, identify who owns the data, calculation, persistence and presentation. Preserve those boundaries. Most regressions happen when logic is moved into the wrong layer or a locked rule is changed while solving an unrelated problem.
