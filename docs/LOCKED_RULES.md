# Locked Rules — MULTIBOT2

**Status:** authoritative. These are **not** defaults to be tuned. A rebuild that
changes any of them is not the same product.

Values are asserted against `config.py` by `tests/test_config.py`,
`tests/test_account_limits.py` and `tests/test_rebuild_spec_inventory.py`.

---

## 1. The eleven invariants

| # | Rule | Value | Where enforced |
|---|---|---|---|
| 1 | **Paper trading only** | Never place a real order. No broker API exists in this codebase. | `dashboard.system.mode` is always `"PAPER"` |
| 2 | **Yahoo Finance is the only provider** | `MARKET_DATA_PROVIDER = "yahoo"` | `config.py:21` |
| 3 | **Exactly 25 assets** | `LIVE_ASSETS` / `LIVE_SYMBOLS` | `config.py:90,198` |
| 4 | **₹100,000 account** | `ACCOUNT_SIZE_INR = 100_000` | `config.py:223` |
| 5 | **₹2,000 risk per trade** | `RISK_PER_TRADE_INR = 2_000` | `config.py:224` |
| 6 | **1.0× leverage — never higher** | `LEVERAGE = 1.0` | `config.py:243` |
| 7 | **Freshness is exactly 1 hour** | `SIGNAL_FRESHNESS_HOURS = 1` | `config.py:16` |
| 8 | **Max 2 sends per signal identity** | `send_count` caps at 2 | `db.py::record_signal_send` |
| 9 | **Supabase authoritative, SQLite fallback** | Never SQLite-only | `db.py`, `schema.sql` |
| 10 | **IST everywhere** | `Asia/Kolkata` | `config.py:14` |
| 11 | **Signals on completed candles only** | `schedule = "completed_candle"` | `strategies/*.py::prepare_candles` |

### The two that are easiest to break by accident

**Rule 7 — freshness is exactly one hour, not a window.** A signal is `FRESH`
only while `age ≤ 1h`. It is not "recent enough", and there is no grace period.
The UI reads the server's `freshness` field and must never recompute it.

**Rule 8 — two sends, hard cap.** `record_signal_send` does
`count = min(count + 1, 2)`. The second send also sets `reminder_sent = 1`,
which retires the reminder. A rebuild that raises this cap re-notifies users
about the same signal indefinitely.

---

## 2. Asset universe — 25 assets

Assembled from four groups in `config.py`:

| Group | Source | Notes |
|---|---|---|
| NSE equities & indices | `NIFTY_SYMBOLS` | India, `09:15`–`15:30` |
| Gold | `GOLD_SYMBOL = "GC=F"` | Futures proxy |
| Bitcoin | `BITCOIN_SYMBOL = "BTC-USD"` | 24/7 |
| Forex | `FOREX_SYMBOLS` | — |

Each `AssetConfig` carries `symbol`, `label`, `yahoo_symbol` (the ticker — may
differ from `symbol`), `market`, `asset_type`, `group`, `sweep_timeframe`.

> **`symbol` ≠ `ticker` in general.** Always send `symbol` to the API and let
> the provider resolve the Yahoo ticker. Never construct a Yahoo ticker client-side.

Sweep hours are asset-class-specific, not global:
```python
BTC_SWEEP_HOURS_IST    = (1, 5, 9, 13, 17, 21)
GOLD_SWEEP_HOURS_IST   = (2, 6, 10, 14, 18, 22)
FOREX_SWEEP_HOURS_IST  = GOLD_SWEEP_HOURS_IST
NSE_INDEX_SWEEP_HOURS_IST = (9, 10, 11, 12, 13, 14)
SWEEP_MINUTE_NSE = 15 ; SWEEP_MINUTE_GLOBAL = 30
```

**Adding or removing an asset is a rule change.** It moves the count off 25,
changes scan timing, and invalidates backtest coverage. Do it deliberately.

---

## 3. Accounts and risk

```python
ACCOUNT_SIZE_INR  = 100_000
RISK_PER_TRADE_INR = 2_000
LEVERAGE          = 1.0
```

Four accounts exist, each with a daily trade cap and a daily planned-risk cap
from `ACCOUNT_TRADE_LIMITS`:

| Account | Daily trade limit | Owner |
|---|---|---|
| `macro` | 20 | `adaptive_trend`, `engulfing_66_sma` |
| `nifty` | 5 | — |
| `ny_session` | 3 | — |
| `sweep_4h` | 3 | `sweep_v2` |

`ACCOUNT_NAMES` is the authoritative tuple; the names and limits are asserted
against it by `tests/test_api_contract.py`.

Position sizing: **risk ÷ distance-to-stop** determines quantity. Leverage 1.0
means no borrowing; the ₹2,000 is a *risk budget*, not a notional cap.

`position_size = RISK_PER_TRADE_INR / risk_per_unit`, where `risk_per_unit` is
`|entry − stop_loss|`. A trade is rejected when `risk_per_unit ≤ 0` — this is
the `NO_TRADE_PLAN` reason.

---

## 4. Signal identity and lifecycle

**Identity.** `signal_key` is derived from strategy + version + symbol +
direction + candle timestamp. It is the dedupe key across the whole system.

**Lifecycle states.** `signal_events.pipeline_status` moves through:
```
RECORDED → … → DELIVERED
```
Terminal set (`signal_lifecycle.TERMINAL`):
`NON_DIRECTIONAL`, `STALE`, `DUPLICATE_LIMIT`, `ACCOUNT_LIMIT`, `NO_TRADE_PLAN`,
`DELIVERED`, `ERROR`.

**Delivery.** `signal_deliveries` records every attempt:
`channel`, `status`, `attempted_at`, `error`, `message_type`. The dashboard
shows the **latest** attempt per signal.

**Actionability.** A signal is `actionable` only when it has all three trade
levels **and** is `FRESH` **and** is not in
`{STALE, ERROR, NO_TRADE_PLAN, ACCOUNT_LIMIT, DUPLICATE_LIMIT}`. Directional,
fresh and non-actionable are three different states. The UI must read the
server's `actionable` flag.

---

## 5. Persistence

**Supabase is authoritative; SQLite is the fallback.** Both hold the same
logical data. Supabase tables: `accounts`, `active_trades`, `closed_trades`,
`sent_signals`, `signal_events`, `signal_deliveries`, `scan_runs`,
`market_data_cache`. SQLite uses a simpler shape (`trades`, `signals`,
`deliveries`) because it is a local cache, not a second source of truth.

`schema.sql` is canonical; `supabase/schema.sql` is a mirror. **Parity is
enforced by `tests/test_schema_parity.py`**, which also asserts that every table
`db.py` writes to actually exists in both.

> Never expose `SUPABASE_KEY` to the browser. It is server-side only, as the
> schema file itself warns.

**Degradation is silent and must stay recoverable.** `db.py` catches `PGRST205`
(missing table) and falls back to SQLite with a warning rather than raising.
That is how the missing `scan_runs` table went unnoticed for so long — a
rebuild must keep the fallback **and** add a test that catches the cause.

---

## 6. Market data

| Rule | Value |
|---|---|
| Provider | Yahoo Finance only (`yfinance`) |
| Default timeframe | `1h` |
| Duration | `SIGNAL_FRESHNESS_HOURS = 1` |
| Cache | Durable, keyed by `cache_key` in `market_data_cache` |
| Validate hourly | `validate_hourly` flag rejects partial/stale hourly bars |

Strategies declare their own data need via `data_request()` and override what
they receive in `prepare_candles()`. A strategy that emits on an incomplete
candle violates rule 11.

Transport failures surface as the reason `MARKET_DATA_ERROR` — never as an
exception that kills a scan. One bad asset must not fail the cycle.

---

## 7. Strategy plug-in rules

1. A strategy lives in `strategies/<id>/strategy.py` with a `__init__.py`.
2. It subclasses `Strategy` and declares a `StrategyManifest`.
3. `discover_strategies()` finds it automatically. **There is no manual
   registration list and no `build_default_registry`.**
4. It returns `Signal` objects. It does **not** place trades, send messages,
   or touch the database.
5. Risk, lifecycle and delivery stay owned by the core bot.
6. Adding a strategy must not require editing any core module. If it does, the
   architecture has regressed.

### The registered three
| Strategy | id | Timeframes | Assets | Account |
|---|---|---|---|---|
| Trend Pulse 1.0.0 | `adaptive_trend` | `1d` | 2 | `macro` |
| Engulf 66 SMA 1.0.2 | `engulfing_66_sma` | `1h` | 25 | `macro` |
| Sweep 4H 2.1.0 | `sweep_v2` | `1h`, `4h` | 25 | `sweep_4h` |

The count (3) and each name/version are asserted against the live registry by
`tests/test_version_consistency.py` and `tests/test_rebuild_spec_inventory.py`.

---

## 8. Notification rules

- Telegram is **optional**. With no `TELEGRAM_BOT_TOKEN` the bot runs fully and
  logs `TELEGRAM_FAILED`. Those log lines are expected, not errors.
- Max 2 sends per `signal_key`, then a single reminder, then silence.
- News pause (`/newspause`) gates delivery without disabling scanning.
- Failed deliveries are surfaced as `health.telegram_failed_deliveries`.

---

## 9. Operational rules

| Rule | Value |
|---|---|
| Bind | `0.0.0.0:$PORT`, default `10000` |
| Health path | `/ping` |
| Startup order | `startup.py` then `main.py` |
| Auth | **None.** Unauthenticated. Do not expose publicly as-is. |
| Keepalive | External cron every 10 min; `/api/health` reports `OK` ≤ 15 min, else `STALE` |
| Python | `>=3.11`; CI uses 3.12 |
| Dependencies | `pandas>=2.2,<3`, `yfinance>=0.2.50,<1`, `requests>=2.31,<3`, `beautifulsoup4>=4.12,<5` |
| Version | `release_notes.APP_VERSION`, mirrored to `pyproject.toml`, `MANIFEST.txt`, `README.md`, `WHATS_NEW.md` |

`/ping` **must not** start a scan or mutate trading state. It exists purely to
keep the free Render service warm.

---

## 10. What a rebuild must never do

```
❌ Place a real trade, or add a broker API
❌ Change or add a data provider other than Yahoo
❌ Relax leverage above 1.0
❌ Emit a signal from an incomplete candle
❌ Recompute freshness, counts, or actionability in the UI
❌ Send a signal more than twice
❌ Make SQLite the sole store
❌ Add a 4th registered strategy without updating the docs and tests
❌ Change a locked value in config.py without updating this file
❌ Expose SUPABASE_KEY to the browser
❌ Rename or remove an API field (see docs/API.md §14)
❌ Introduce a second source of truth for version or schema
```
