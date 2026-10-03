# API Contract — MULTIBOT2

**Status:** authoritative. Derived from `main.py`, `dashboard.py`, `signal_lifecycle.py`
and `db.py` at **v3.3.0**. Guarded by `tests/test_api_contract.py`.

**Why this file exists.** The server is a hand-rolled `wsgiref` application with
routing written inline in `main.py::web_server().app()`. There is no OpenAPI
document, no route table and no response-schema test. The dashboard is the only
consumer, and the only thing that knows the exact payload shape is the minified
rendering code in `app.js`. That makes a UI-only rebuild guesswork.

This document is the seam. A new front end may be written against this file alone.

---

## 1. Transport rules

| Rule | Value |
|---|---|
| Server | `wsgiref.simple_server`, `0.0.0.0:$PORT` |
| Port | `PORT` env var, default `10000` |
| JSON content type | `application/json; charset=utf-8` |
| JSON cache header | `Cache-Control: no-store` |
| Static cache header | `Cache-Control: no-store` |
| Serialization | `json.dumps(payload, default=str)` — **non-serializable values are stringified, never dropped** |
| Auth | **None.** The server is unauthenticated. Do not expose publicly without adding auth. |
| CORS | None. Same-origin only. |

Because of `default=str`, a `pandas.Timestamp`, `Decimal` or `numpy.float64`
that leaks into a payload arrives as its `str()` form. Consumers must parse
defensively rather than assume a type.

### Time and number conventions
- All timestamps are **ISO-8601 strings**. Those with an offset are IST
  (`Asia/Kolkata`); naive ones are read as IST by the backend.
- Money is **unformatted numbers** (float), not strings. The UI formats to `₹`
  using `en-IN` grouping. See `app.js::inr`.
- Percentages are **numbers already in percent units** (`12.5` means 12.5%).
- **Null is meaningful.** `null` means "not set", which is distinct from `0`.
  `app.js` renders `null` as an em-dash `—`, never as `0`.

---

## 2. Route table

| Method | Path | Query params | Success | Failure |
|---|---|---|---|---|
| GET | `/` | — | 200 `text/html` | 404 |
| GET | `/dashboard` | — | 200 `text/html` | 404 |
| GET | `/ping` | — | 200 `text/plain` → `pong` | — |
| GET | `/api/health` | — | 200 JSON | **503** JSON |
| GET | `/api/dashboard` | — | 200 JSON | **500** JSON |
| GET | `/api/diagnostics/sweep` | `period` (default `30d`) | 200 JSON | **500** JSON |
| GET | `/api/calendar` | `date`, `impact`, `refresh` | 200 JSON | **400** JSON |
| GET | `/api/news` | identical — **alias of `/api/calendar`** | 200 JSON | **400** JSON |
| GET | `/api/backtest` | `strategy`, `symbol`, `period` | 200 JSON | **400** JSON |
| GET | `/api/settings` | — | 200 JSON | — |
| POST | `/api/settings` | body (see §11a) | 200 JSON | **400** JSON / **405** JSON |
| GET | `/architecture` | — | 200 `text/html` | 404 |

### Static assets (`main.py::web_server`, the `files` dict)

| Path | File | Content type |
|---|---|---|
| `/` | `dashboard.html` | `text/html; charset=utf-8` |
| `/dashboard` | `dashboard.html` | `text/html; charset=utf-8` |
| `/app.js` | `app.js` | `application/javascript` |
| `/styles.css` | `styles.css` | `text/css` |
| `/foundation.css` | `foundation.css` | `text/css` |
| `/appearance-overrides.css` | `appearance-overrides.css` | `text/css` |
| `/appearance.js` | `appearance.js` | `application/javascript` |
| `/dashboard-live-wiring.js` | `dashboard-live-wiring.js` | `application/javascript` |

> **Adding a UI asset means adding a route.** There is no directory listing and no
> catch-all static handler. A new file that is not in the `files` dict returns 404.
> A new UI therefore touches `main.py`. That is the one server change a UI
> rebuild is allowed to make.

**CSS load order is a contract** (as declared in `dashboard.html`, not the server):
`styles.css` → `foundation.css` → `appearance-overrides.css`. Later sheets win
at equal specificity. `styles.css` is the only sheet that declares contrast
tokens.

---

## 3. Error envelope

Three different shapes exist. Handle all of them.

```jsonc
// /api/health and /api/dashboard
{"ok": false, "status": "DEGRADED", "error": "<message>", "timestamp": "<iso>"}

// /api/diagnostics/sweep  — the only endpoint with error_type
{"ok": false, "error_type": "<ExceptionClass>", "error": "<message>"}

// /api/calendar, /api/news, /api/backtest
{"ok": false, "error": "<message>"}
```

`ok: true` is present on every success response. **A rebuild should branch on
`ok`, not on HTTP status alone** — `api/health` deliberately returns `503` with
a well-formed body so a monitor can read the reason.

---

## 4. `GET /ping`

The keepalive endpoint. External cron (cron-job.org every 10 min in
`render.yaml`) hits it to keep the free Render service warm.

- **200** `text/plain`, body `pong`, `Cache-Control: no-store`.
- **Side effect:** updates the module-level `LAST_PING_AT`.
- **Explicitly does NOT** start a scan, touch the database, or mutate trading
  state. This is stated in `render.yaml` and is load-bearing.
- `/api/health` computes `keepalive` from this value: `OK` when the ping is
  ≤ 15 minutes old, `STALE` beyond that, `UNKNOWN` if never pinged.

---

## 5. `GET /api/health`

Liveness plus operational facts. Cheap; safe to poll.

```jsonc
{
  "ok": true,
  "status": "ONLINE",              // or "DEGRADED" on 503
  "version": "3.3.0",              // release_notes.APP_VERSION
  "timestamp": "2026-10-01T09:30:00+05:30",
  "runtime": true,                 // false once startup sequence failed
  "database": "SUPABASE+SQLITE",   // or "SQLITE_FALLBACK"
  "scheduler": true,               // false when STOP event is set
  "strategies": 3,                 // count from the live registry
  "provider": "yahoo",             // config.MARKET_DATA_PROVIDER
  "telegram": "CONFIGURED",        // or "DISABLED" when no bot token
  "keepalive": "OK",               // "OK" | "STALE" | "UNKNOWN"
  "last_ping_at": "2026-10-01T09:20:00+05:30",  // null if never
  "keepalive_age_minutes": 10.0    // null if never
}
```

---

## 6. `GET /api/dashboard`

**The entire UI.** One request drives all five pages. The client polls this
every `CONFIG.refreshMs` (30 000 ms) and appends `?t=<Date.now()>` to defeat
caching.

Built by `dashboard.py::build_dashboard_snapshot()`.

```jsonc
{
  "ok": true,
  "version": "3.3.0",
  "generated_at": "2026-10-01T09:30:00+05:30",
  "whats_new": ["…"],                       // config.WHAT_IS_NEW → release_notes

  // ── Locked operating rules, echoed so the UI never hardcodes them ──────
  "system": {
    "status": "ONLINE",
    "mode": "PAPER",                       // always "PAPER"
    "timezone": "Asia/Kolkata",
    "provider": "YAHOO",
    "freshness_hours": 1,
    "leverage": 1.0
  },
  "rules": {
    "account_size_inr": 100000,
    "risk_per_trade_inr": 2000,
    "account_trade_limits": { "<account>": <int> }
  },

  // ── Asset universe ─────────────────────────────────────────────────────
  "universe": {
    "count": 25,
    "symbols": ["RELIANCE.NS", "…"],
    "asset_metadata": [{
      "symbol": "RELIANCE.NS",
      "label": "Reliance Industries",
      "ticker": "RELIANCE.NS",             // Yahoo ticker — may differ from symbol
      "market": "NSE",
      "asset_type": "EQUITY",
      "group": "…",
      "sweep_timeframe": "15"               // minutes; null where not swept
    }]
  },

  // ── Backtestable assets (different, smaller set than the universe) ─────
  "backtest_assets": [
    {"key": "RELIANCE.NS", "ticker": "…", "label": "…", "group": "…"}
  ],

  // ── Registered strategies, straight from the live registry ─────────────
  "strategies": [{
    "id": "adaptive_trend",
    "name": "Trend Pulse",
    "version": "1.0.0",
    "description": "…",
    "assets": ["…"],
    "timeframes": ["1d"],
    "schedule": "completed_candle",
    "account": "macro",
    "capabilities": ["signal", "fixed_sl", "fixed_tp", "backtest"],
    "parameters": { "<key>": {"type": "…", "default": …, "min": …, "max": …,
                              "options": [...], "editable": …} }
  }],

  "accounts": {
    "count": 4,
    "names": ["macro", "nifty", "ny_session", "sweep_4h"],
    "data": [{
      "name": "macro",
      "starting_balance": 100000.0,
      "balance": 100000.0,
      "planned_risk_used": 0.0,
      "daily_trade_limit": 20,
      "max_daily_planned_risk": 40000.0,
      "trades_today": 0,
      "remaining_trades": 20,
      "remaining_planned_risk": 40000.0
    }]
  },

  "signals": [ /* see §7 */ ],
  "trades":   [ /* see §8 */ ],

  // ── Live scan state ────────────────────────────────────────────────────
  "scan": {
    "status": "OK",              // "NOT_RUN" | "OK" | "PARTIAL" | "ERROR" | …
    "at": "2026-10-01T09:29:00+05:30",
    "checked": 25,
    "directional": 4,
    "sent": 1,
    "errors": 0,
    "strategies": { "<strategy_id>": { /* per-strategy row */ } }
  },

  // ── Durable scan history (History → Scan History) ──────────────────────
  "scan_history": [{
    "id": "…", "strategy_id": "…",
    "started_at": "…", "finished_at": "…",
    "status": "OK",
    "payload": {"checked": 25, "directional": 4, "sent": 1, "errors": 0}
  }],

  "health": {
    "database": "SUPABASE+SQLITE",
    "provider": "YAHOO",
    "telegram": "CONFIGURED",
    "telegram_failed_deliveries": 0,
    "open_trades": 0,
    "signal_lifecycle": "ENABLED"
  },

  // ── Precomputed counts — use these, do not recount client-side ─────────
  "counts": {
    "signals": 12, "directional_signals": 4,
    "fresh_directional": 3, "stale_directional": 1,
    "trades": 2, "open_trades": 1, "closed_trades": 1
  },
  "signal_summary": {
    "total_directional": 4,
    "fresh": 3,
    "stale": 1,
    "delivery": {"SENT": 1, "NOT_SENT": 3},   // counts keyed by delivery status
    "latest": { /* the newest directional signal, or null */ }
  }
}
```

### Limits the client must respect
- `signals` is capped at **500** rows (`DB.load_signal_history(500)`).
- `scan_history` is capped at **50** rows (`DB.load_scan_runs(50)`).
- `trades` is **uncapped**.

### Derived-by-backend, not by the client
`directional` = `signal`/`direction` ∈ `{BUY, SELL}`.
`fresh_directional` = directional **and** `freshness == "FRESH"`.
`stale_directional` = directional **and** `freshness == "STALE"`.
The server does this so every page agrees. Recomputing it client-side is a bug.

---

## 7. Signal object

Produced by `signal_lifecycle.dashboard_signal()`. It is the **stored event row
plus eleven computed fields**. Stored fields are passed through unchanged.

### Stored fields (from `signal_events`)
`signal_id`, `signal_key`, `strategy`, `strategy_version`, `version`, `symbol`,
`direction`, `signal`, `timestamp`, `timeframe`, `reason`, `pipeline_status`,
`metadata`, `created_at`, `updated_at`.

> `signal` is an **alias of `direction`**. `strategy_version` is an alias of
> `version`. Both exist for backward compatibility; read either.

### Computed fields — the contract
| Field | Type | Meaning |
|---|---|---|
| `entry` | number \| null | Promoted from `metadata.entry` if the column is null |
| `stop_loss` | number \| null | same promotion from `metadata.stop_loss` |
| `take_profit` | number \| null | same promotion from `metadata.take_profit` |
| `freshness` | `"FRESH"` \| `"STALE"` \| … | From `signal_gate.signal_status` |
| `age_minutes` | int | `max(0, age_hours * 60)` |
| `send_count` | int | **0, 1 or 2. 2 is the hard cap.** |
| `first_sent_at` | string \| null | |
| `last_sent_at` | string \| null | |
| `delivery` | object \| null | Latest delivery row, or null if never attempted |
| `has_trade_levels` | bool | `entry`, `stop_loss`, `take_profit` **all** non-null |
| `actionable` | bool | See below |

```jsonc
// delivery, when present
{"status": "SENT", "attempted_at": "…", "error": null, "message_type": "…"}
```

### `actionable` — the single most important derived flag
```python
has_trade_levels and freshness == "FRESH"
and pipeline_status not in {STALE, ERROR, NO_TRADE_PLAN, ACCOUNT_LIMIT, DUPLICATE_LIMIT}
```
A signal can be directional and fresh and still not be actionable. The UI must
read `actionable`, never infer it.

### Degradation rule (deliberate)
A malformed historical row **never** fails the endpoint. It degrades to
`freshness: "STALE"`, `age_minutes: 0` and logs a warning. The dashboard must
tolerate individual bad rows.

---

## 8. Trade object

```jsonc
{
  "id": "…",
  "status": "OPEN",                    // "OPEN" | "CLOSED"
  "symbol": "…", "label": "…",
  "market": "NSE", "asset_type": "EQUITY", "group": "…",
  "account": "macro",
  "strategy": "…", "strategy_version": "…",
  "type": "BUY",                       // the plan side
  "entry": 0.0, "sl": 0.0, "tp": 0.0, "qty": 0.0,
  "planned_risk": 2000.0,
  "signal_ts": "…", "opened_at": "…",
  "exit_price": null, "exit_timestamp": null, "closed_at": null,
  "pnl": null,                         // null while OPEN
  "result": null, "exit_reason": null,
  "plan": {                            // nested, denormalised plan
    "strategy": "…", "strategy_version": "…", "side": "BUY",
    "signal_timestamp": "…", "timeframe": "1h",
    "entry": 0.0, "stop_loss": 0.0, "take_profit": 0.0,
    "risk_per_unit": 0.0, "trailing_policy": "…"
  }
}
```

`type` and `plan.side` are the same value. `pnl`, `result` and `exit_price` are
`null` until the trade closes — **this is how the UI distinguishes open from
closed without relying on `status` alone.**

---

## 9. `GET /api/calendar` (and `/api/news`)

| Param | Format | Default |
|---|---|---|
| `date` | `YYYY-MM-DD` | today (IST) |
| `impact` | comma-separated, title-case: `All`, `High`, `Medium`, `Low`, `Holiday` | `All` |
| `refresh` | `1` forces a re-fetch; anything else uses cache | off |

Returns `NEWS.get(target_date=…, impacts=…, force=…)` — parsed Forex Factory
calendar events. `impacts` containing `All` collapses to `{"All"}`.

Verified top-level shape (v3.3.0, live):
```jsonc
{
  "cache_policy": { … },     // freshness/cache metadata
  "calendar_url": "https://www.forexfactory.com/calendar",
  "counts": { … },           // impact tallies used by the summary tiles
  "date": "2026-10-01",
  "days": [ … ],             // per-date groups, each expandable in the UI
  "fetched_at": "…"
}
```
The dashboard's four impact tiles (`impactCountall` / `high` / `medium` / `other`)
read `counts`; the date list reads `days`. Keep that mapping — the ids are part
of the client contract even though the shape is upstream-defined.

> **Upstream dependency.** This endpoint scrapes an external site with
> BeautifulSoup. Its shape can change without notice and it can fail. The UI
> must render an error state here, not a blank page. It is the one endpoint
> that is allowed to be unavailable while the bot is healthy.

---

## 10. `GET /api/backtest`

| Param | Default | Notes |
|---|---|---|
| `strategy` | first registered strategy id | must exist in the registry |
| `symbol` | first of `LIVE_SYMBOLS` | must be in that strategy's `manifest.assets`, else **400** |
| `period` | `30d` | Yahoo range string |

```jsonc
{
  "ok": true,
  "strategy": "Engulf 66 SMA",
  "strategy_id": "engulfing_66_sma",
  "strategy_version": "1.0.2",
  "symbol": "RELIANCE.NS",
  "asset": {"ticker": "…", "label": "…", "group": "…"},
  "period": "30d",
  "parameters": { … },
  "candle_count": 480,
  "buy_signals": 9, "sell_signals": 6,
  "trades_taken": 4,
  "planned_risk": 8000.0,             // trades_taken × RISK_PER_TRADE_INR
  "equity_curve": [{"timestamp": "…", "equity": 100000.0}, …],
  "metrics": {
    "return_pct": 0.0, "max_drawdown_pct": 0.0,
    "sharpe": 0.0, "sortino": 0.0,
    "win_rate_pct": 0.0, "profit_factor": 0.0,
    "number_of_trades": 0, "average_trade": 0.0,
    "max_losing_streak": 0, "exposure_pct": 0.0,
    "risk_adjusted_performance": 0.0,
    "rating": 0, "rating_label": "…", "breakdown": { … }
  },
  "daily": [{"date": "2026-09-01", "buy": 1, "sell": 0, "total": 1}],
  "signals": [ /* directional only, last 200 */ ],
  "trades":  [ /* last 200: timestamp, direction, entry, exit, pnl, bars_held */ ],
  "generated_at": "…"
}
```

The equity curve is **always at least one point** (the starting account), even
when zero trades occur. Render an empty chart, never a crash.

`rating`, `rating_label` and `breakdown` are display-only; the UI shows
`rating_label` and omits the other two from the metrics grid.

---

## 11. `GET /api/diagnostics/sweep`

Runs the real Sweep V2 path (fetch → `prepare_candles` → signal) **without
dispatching or sending**.

| Param | Default |
|---|---|
| `period` | `30d` |

```jsonc
{
  "ok": true,
  "strategy": {"id": "sweep_v2", "name": "…", "version": "…"},
  "generated_at": "…",
  "period": "30d",
  "totals": {"assets": 25, "ok": 0, "errors": 0, "directional": 0,
             "reasons": {"MARKET_DATA_ERROR": 1}},
  "assets": [{
    "symbol": "…", "label": "…", "market": "…", "timeframe": "…",
    "raw_candles": 480, "prepared_candles": 60,
    "direction": null,                 // null when non-directional
    "reason": "MARKET_DATA_ERROR"      // gate reason when it did not signal
  }]
}
```

`reason` values include `MARKET_DATA_ERROR` and the `signal_gate` reasons.

---

## 11a. `/api/settings` — accounts, assets and routing

These values decide which account takes a real trade and on how much capital,
so they are written on the server. An unsaved edit is never applied, and a
refused one leaves the running configuration exactly as it was.

`GET` returns the live document plus the compiled-in defaults:

```jsonc
{
  "ok": true,
  "settings": {
    "accounts": [{"name": "macro", "starting_balance": 100000,
                  "daily_trade_limit": 20, "risk_per_trade": 2000}],
    "assets":   [{"symbol": "TATAMOTORS", "label": "Tata Motors",
                  "yahoo_symbol": "TATAMOTORS.NS", "market": "NSE",
                  "asset_type": "equity", "group": "NSE Stocks", "currency": "INR",
                  "sweep_timeframe": "4H", "strategies": ["engulfing_66_sma"]}],
    "session":  {"timezone": "America/New_York", "start_hour": 8, "end_hour": 17},
    "rules":    [{"account": "macro", "strategies": ["adaptive_trend", "engulfing_66_sma"],
                  "asset_groups": ["Global Markets"], "in_ny_session": false}],
    "options":  {"account_groups": ["NSE Stocks", "NSE Indices", "Global Markets"],
                 "strategies": ["adaptive_trend", "engulfing_66_sma", "sweep_v2"],
                 "strategy_names": {"sweep_v2": "Sweep 4H"},
                 "asset_types": ["equity", "index", "commodity", "crypto", "forex"],
                 "currencies": ["INR", "USD"],
                 "limits": {"min_size": 1000, "max_size": 100000000,
                            "min_trade_limit": 1, "max_trade_limit": 500,
                            "min_risk": 100, "max_risk": 500000}}
  },
  "defaults": { /* same shape */ }
}
```

`POST` takes `{"settings": { /* same shape, minus `options` */ }}`, or
`{"settings": {"action": "reset"}}` to go back to `config.py`.

```jsonc
// 200 OK
{"ok": true, "settings": { /* applied */ }, "message": "Settings saved and applied to the running bot."}

// 400 Bad Request — nothing was applied
{"ok": false, "error": "Session start hour must be earlier than the end hour",
 "settings": { /* the configuration still in force */ }}
```

**What an operator may change.** The four built-in accounts (`macro`, `nifty`,
`ny_session`, `sweep_4h`) and the 25 shipped assets are the shipped contract:
they keep their values and cannot be deleted. Everything else is free — add an
account with its own capital, daily limit and risk; add an asset to an
*existing* account group; retime the New York window; reorder routing.

**Refusals** are written to be shown verbatim in the UI. They cover: an unknown
account, strategy or asset group; duplicate names; an empty selection; a start
hour not earlier than the end hour; not exactly one rule per account; an
uncovered asset group; an account no signal could ever reach; and an account
whose daily risk budget does not fit inside its own starting balance.

Sweep timeframe and currency are **derived from the asset's group**, not taken
from the client, because the sweep engine needs a closed candle at that
resolution.

`GET /api/dashboard` echoes the same table under `rules.account_routing`,
`rules.new_york_session` and `rules.accounts`.

---

## 12. Client contract

From `app.js` / `dashboard-live-wiring.js`. A rebuild must preserve these.

```js
const CONFIG = {
  apiUrl: window.DASHBOARD_API_URL || "/api/dashboard",  // overridable
  timezone: "Asia/Kolkata",
  refreshMs: 30000
};
```

### Rendering helpers that carry contract, not taste
| Helper | Contract |
|---|---|
| `escapeHtml(v)` | Escapes `& < > " '`. **Every** interpolated value must pass through it. |
| `inr(v)` | `₹` + `en-IN`, 0–2 fraction digits. Non-finite → `—`. |
| `number(v, d)` | `en-IN`, fixed decimals. Non-finite → `—`. |
| `timestamp(v)` | IST, `en-IN`, `hour12: false`. Invalid → `—`. |
| `dateKey(v)` | `YYYY-MM-DD` in IST via `en-CA` (used for grouping). |
| `dateLabel(v)` | Parses `${key}T00:00:00` as **local**, not IST — deliberate, so the day label never shifts. |

**The `—` em-dash convention is load-bearing.** `null`, `undefined` and
non-finite all render `—`, never `0`, `NaN` or an empty cell. An empty state
must have real explanatory copy, not a blank.

### Five pages
`#page-overview` · `#page-signals` · `#page-history` · `#page-calendar` ·
`#page-tools`. Exactly one is displayed at a time; hidden pages are
`display:none`, so **exactly one `<h1>` is in the accessibility tree**.

### Data attributes the wiring depends on
`data-page`, `data-page-link`, `data-expand` (signal card body),
`data-signal-date`, `data-history-date` + `data-history-kind`
(`"open"` | `"scan"`), `data-calendar-date-group`, `data-tool-key`,
`data-trade-index`, and the appearance hooks `data-style-choice`,
`data-theme-choice`, `data-accent-choice`, plus `data-style`, `data-theme`,
`data-accent` on `<html>`. See `THEME_SYSTEM.md`.

---

## 13. Versioning rule

`version` appears in `/api/health` and `/api/dashboard` and always equals
`release_notes.APP_VERSION`. **The UI must render the value it receives**, never
a hardcoded or build-time version — `tests/test_version_consistency.py` and
`tools/check_release_docs.py` enforce that one string across 5 files.

## 14. Compatibility rule for a rebuild

Adding a field is safe. Removing or renaming one, changing a unit, flipping a
`null` into a default, or changing a status string is a **breaking** change.

Because the dashboard is the only consumer and the payloads are produced by
`default=str`, a rebuild should treat every value as "possibly stringified,
possibly null" and re-verify against a live instance before shipping.