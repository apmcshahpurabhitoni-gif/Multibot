# MULTIBOT2 — CANONICAL WIRING & HANDOFF

## Purpose
This file freezes the wiring that has been audited and accepted for the current UI branch. Future UI work must preserve these contracts unless a deliberate backend/wiring change is requested.

## Branch / baseline
- Repository: apmcshahpurabhitoni-gif/Multibot
- Working branch: ui/figma-mavis-redesign
- Production main must remain untouched until explicitly approved.
- Current dashboard UI is considered wired correctly at the presentation layer.

## Frontend loading order
dashboard.html loads scripts in this order:
1. dashboard-live-wiring.js
2. app.js
3. appearance.js

Reason: dashboard-live-wiring.js wraps fetch before app.js performs its initial /api/dashboard request. This prevents first-load data from being missed.

## Dashboard API contract
- Primary endpoint: /api/dashboard
- app.js owns the primary API request/error handling.
- dashboard-live-wiring.js observes /api/dashboard responses and updates live dashboard sections.
- API responses must be HTTP-success, valid JSON objects, and contain the expected dashboard snapshot shape before rendering.
- Presentation bridge errors must never convert a successful dashboard fetch into a failed runtime request.

## Frontend ownership
### app.js
Owns:
- dashboard bootstrap and refresh
- page navigation
- overview rendering
- signals rendering
- history rendering
- tools/backtest rendering
- calendar loading/rendering
- expand/collapse state for canonical cards/groups
- API error/loading handling
- 30-second refresh cadence
- asset and strategy labeling from dashboard metadata

### dashboard-live-wiring.js
Owns presentation updates derived from the live dashboard payload, including:
- open positions
- scan status/history
- live dashboard sections not owned by canonical app.js renderers
- scan-history grouping by Asia/Kolkata date
- bridge-safe fetch interception

### appearance.js
Owns presentation-style state:
- Modern / Neo style
- localStorage persistence for style
- data-style and style classes
- style-choice button state
- style click handling
It is presentation-only and must not change trading logic.

### appearance-overrides.css / mavis-ui.css / styles.css
CSS only. No trading/backend state mutation.

## Current UI data flow
Backend runtime
  -> /api/dashboard
  -> app.js primary loader
  -> canonical state
  -> Overview / Signals / History / Calendar / Tools

The live wiring bridge also observes the same successful dashboard response:
  /api/dashboard
  -> dashboard-live-wiring.js
  -> open trades + scan status/history presentation

## Backend runtime flow
Yahoo Finance
  -> market-data validation/cache
  -> canonical candles
  -> strategy registry/plugin
  -> canonical Signal
  -> completion check
  -> freshness <= 1 hour
  -> duplicate identity gate
  -> account/risk validation
  -> TradePlan
  -> Supabase authoritative persistence / SQLite fallback
  -> Telegram output
  -> dashboard snapshot

No directional signal = no trade and no Telegram signal dispatch.

## Locked runtime facts
- Paper trading only; no live broker orders.
- Provider: Yahoo Finance.
- Timezone: Asia/Kolkata.
- Signal freshness: exactly 1 hour.
- Primary persistence: Supabase.
- Fallback/local persistence: SQLite.
- Starting account: ₹100,000.
- Base risk/trade: ₹2,000.
- Leverage: 1x.
- Fixed live universe: 25 assets.
- Signal identity: strategy + symbol + direction + candle timestamp.
- Maximum sends per identity: 2 (initial + one reminder).
- Scanning itself does not consume send allowance.

## Asset presentation
Dashboard asset labels come from backend universe metadata where available. UI should display simple human labels (for example Gold, Bitcoin, Reliance) while retaining canonical backend symbols/tickers.

## Backtest wiring
Tools page controls:
- strategy selector
- selectable asset selector
- period selector
- run button
- status/result area

Backtest results are rendered from backend data. Do not replace selectable assets with free-text symbol entry unless explicitly requested.

## History / scan history
- Signals and completed trades are grouped consistently by Asia/Kolkata date.
- Scan history is grouped by date and retains up to 50 rows before grouping.
- Open trades are displayed separately from completed history.
- Duplicate directional signals are canonicalized by signal identity before presentation.

## Appearance persistence
- Style key: mavis-style
- Theme key: mavis-theme
- Valid styles: modern, neo.
- Neo mode is represented through data-style="neo" plus neo-mode class.
- Do not create a second style owner or competing style persistence mechanism.

## Event ownership
Primary controls currently wired:
- desktop/mobile navigation
- refresh
- signals refresh
- history refresh
- calendar refresh
- theme toggle
- theme selection
- style selection
- compact mode
- reduce motion
- backtest strategy/asset/period
- run backtest
- calendar/signal/history expansion

Do not bind the same interaction twice in a new script.

## Known legacy code
app.js still contains legacy render functions/IDs for older dashboard sections (including renderTrades/renderScanStatus/renderScanHistory and IDs such as tradesTotalCount, tradesOpenCount, tradesClosedCount, tradesResultCount, tradesList, scanStatus, scanHistory). They are not part of the canonical current bootstrap/render flow. Do not remove them casually; preserve runtime behavior unless cleanup is explicitly requested.

## Backend safety / preservation
The current UI branch is a presentation/wiring pass. Do not alter:
- risk rules
- freshness rule
- duplicate gate
- strategy contracts
- candle completion rules
- account limits
- provider policy
- persistence semantics
- Telegram lifecycle semantics
unless the task explicitly requests a backend behavior change.

## Known historical backend issues
These were identified in earlier audits and are separate from the now-stable UI wiring:
- FX sizing bug related to D-004.
- Backtest bypassing prepare_candles / Completed Candle Rule.
- Supabase signal_events POST 404.
- Telegram polling conflict HTTP 409.
- yfinance NumPy timedelta deprecation warning.

These items require a separate backend audit/fix pass and must not be silently changed as part of UI work.

## Validation before merge
Run:
- python -m compileall -q .
- pytest
- import runtime modules
- verify /ping
- verify /api/dashboard returns valid JSON
- verify dashboard first-load data
- verify refresh
- verify all five pages
- verify style/theme persistence
- verify backtest request/result
- verify mobile navigation
- verify open trades and scan history
- verify no duplicate UI event ownership

## Change discipline
1. Inspect before changing.
2. Preserve trading logic.
3. Make one coherent change at a time.
4. Validate the affected wiring.
5. Run the full test suite before merge.
6. Never merge to main merely because the UI looks correct.
7. Update this file whenever an accepted wiring contract changes.

## Canonical source note
This document is the handoff contract for the accepted UI/data wiring state. If future work starts in a new chat, read this file first, then inspect the actual branch files before modifying anything.
