# MULTIBOT2 — Master Audit & Fix Notes

**Status:** Working master plan — audit/fix boundary  
**Date:** 2026-10-06  
**Repository:** `apmcshahpurabhitoni-gif/Multibot`  
**Current release audited:** v3.5.0  
**Principles:** Frozen architecture + Ponytail engineering + UX/UI Pro Max + Jakub Krehel Skills methodology

---

## 0. Non-negotiable boundary

This document is the master handoff for the next MULTIBOT2 work.

### Do not change

- Trading strategy logic unless a confirmed defect requires it.
- Paper-only mode.
- Yahoo Finance as the market-data provider.
- 1.0× leverage ceiling.
- 1-hour signal freshness.
- Two-send signal identity cap.
- Completed-candle rule.
- Server-owned signal freshness/actionability/counts.
- Plugin/registry architecture.
- Supabase-authoritative + SQLite fallback contract.
- Existing API field contracts without deliberate migration.
- Asset/account locked rules.

### Engineering rule

**Fix the system at the correct boundary. Do not patch symptoms page-by-page or strategy-by-strategy.**

---

# 1. Audit baseline — confirmed runtime/backend findings

## P0 / High — Backtest does not fully honor account-specific risk

### Finding

Live sizing passes the resolved account into:

`quantity_for_risk(..., account=account)`

But the backtest path currently calls:

`quantity_for_risk(entry, sl, fx_rate=fx_rate)`

without the account.

The dashboard resolves the account before calling the backtest, but the simulation/reporting still uses global `ACCOUNT_SIZE_INR` / `RISK_PER_TRADE_INR` values in important places.

### Impact

A user can configure a non-default account in Tools and receive correct live sizing while the backtest uses different capital/risk assumptions.

### Required fix

Backtest must use the selected account as the single source for:

- starting balance
- risk per trade
- daily trade limit
- quantity sizing
- planned risk
- equity curve
- summary metrics

### Regression test

Create a non-default account with different capital/risk and prove the backtest result changes accordingly.

**Do not redesign the backtest architecture. Fix the account/risk boundary.**

---

# 2. High — Public unauthenticated configuration API

## Finding

The dashboard/API is intentionally unauthenticated.

`/api/settings` can modify accounts, assets, routing and risk configuration.

### Impact

If deployed publicly, an external user may be able to modify bot configuration.

### Required resolution

Before public exposure, protect the application using an explicit authentication/access-control boundary.

This is a **deployment/security blocker**, not a reason to silently redesign the application's core architecture.

---

# 3. Medium — Supabase fallback semantics need explicit verification

## Finding

Documentation describes:

> Supabase authoritative; SQLite fallback.

Some Supabase failure paths may raise rather than transparently fall back/reconcile.

### Required work

Audit each write/read boundary and classify:

- true fallback
- intentional hard failure
- recoverable retry
- silent degradation

Then add tests for the intended behavior.

**Do not change persistence semantics until the intended contract is explicit.**

---

# 4. Medium — Documentation contradiction

Current authoritative rules say:

- **25 shipped assets**

Older documents still contain:

- **19 live assets**

Affected documentation includes older rebuild/finalization specifications.

### Required fix

Make documentation internally consistent with v3.5.0.

Preferred approach:

- `docs/LOCKED_RULES.md` = authoritative runtime contract.
- Older 19-asset documents = update or explicitly mark historical/obsolete.
- Version all rebuild documents.
- Never allow an AI/developer rebuild document to contradict the current runtime contract.

No runtime logic change is required.

---

# 5. Medium — Strategy/provider completed-candle ownership needs clarification

`strategy_engine.py` currently fetches provider data with:

`validate_hourly=False`

Strategies then perform their own completed-candle preparation.

Current strategies appear to have their own safeguards, so this is **not yet classified as a confirmed trading bug**.

### Required work

Document exactly which layer owns:

1. provider data validation
2. candle completeness
3. strategy-specific aggregation
4. completed-candle filtering

Then add tests proving an incomplete candle cannot reach `generate_signal()`.

**Do not simply switch the flag without understanding the architecture.**

---

# 6. Current production incident — repeated sweep_v2 errors

## User-visible symptom

Telegram repeatedly sends:

> ERROR — SCAN sweep_v2

> MARKET_DATA_ERROR: OHLC data contains invalid values

> Paper mode remains active.

The screenshots show repeated occurrences across multiple scan cycles.

## Important distinction

There are **two bugs**, not one.

### Bug A — invalid market data

`market_data.normalize_candles()` rejects required OHLC values after numeric coercion when they become invalid/NaN.

This validation is correct.

### Bug B — repeated scan-level Telegram errors

The existing silence mechanism contains:

`MARKET_DATA_ERROR`

in `NotificationService._silent_reasons`.

However, the screenshot is a **scan-level** error.

`main._notify_scan()` sends scan notifications with `audit=False`.

Therefore the signal-event silence gate does not apply.

### Required resolution

1. Identify exact affected symbol(s).
2. Capture Yahoo interval/request.
3. Capture raw returned OHLC.
4. Identify the invalid candle/field.
5. Trace cache involvement.
6. Preserve strict validation.
7. Record the failure in scan history/dashboard/logs.
8. Suppress/deduplicate repeated scan-level market-data error Telegram messages.
9. Add regression tests for repeated failures.
10. Reconcile release notes with actual behavior.

### Never do this

- Do not convert invalid OHLC to zero.
- Do not forward-fill bad OHLC blindly.
- Do not ignore NaN candles.
- Do not weaken validation simply to stop Telegram spam.
- Do not disable sweep_v2 as a permanent workaround.

---

# 7. UX/UI audit — core systemic problems

The dashboard audit identified the following root causes.

## P0/P1 — CSS cascade war

Approximately 2,986 `!important` declarations exist across:

- `styles.css`
- `foundation.css`
- `appearance-overrides.css`

### Impact

The same component can be controlled by several competing rules.

This directly contributes to:

- border inconsistencies
- overlap
- clipping
- inconsistent text
- theme-specific regressions
- unpredictable future changes

### Required fix

Establish one predictable cascade:

`tokens → base → components → theme layers`

Theme changes should primarily remap tokens, not repeatedly override component properties.

---

# 8. UX/UI — two token systems

Current system has:

- main semantic tokens
- `--f-*` foundation tokens

with hardcoded values leaking around both.

### Required fix

Create one canonical token vocabulary.

Foundation tokens may be aliased during migration, but components must consume the canonical semantic tokens.

---

# 9. UX/UI — shape/radius inconsistency

Measured styles contain multiple unrelated radii.

Examples:

- Modern: 9/11/12/18px
- Material 3: 12/18px/pills
- Neo: 7/9/18px

### Required fix

Define shape tiers per style.

Example concept:

- outer surface
- nested surface
- control
- pill

Components must consume shape tokens.

No random `8px`, `9px`, `10px` radius values scattered through component CSS.

---

# 10. UX/UI — accent parity

Five accents are supported:

- emerald
- indigo
- amber
- rose
- cyan

All three styles must resolve all five accents consistently.

### Current defect

Neo does not map every accent explicitly, causing a selected accent to fall back to a different visual hue.

### Required fix

Build and test the complete:

**3 styles × 5 accents × 2 themes = 30 combinations**

matrix.

---

# 11. UX/UI — typography

Current audit found extremely small text values around 8–8.5px.

### Required fix

- Remove tiny UI labels.
- Minimum practical UI text around 11–12px.
- Prefer 12px for compact metadata.
- Keep normal body text comfortably readable.
- Preserve 16px input sizing where mobile zoom is relevant.

---

# 12. UX/UI — accessibility gaps

## Reduced motion

Add:

`@media (prefers-reduced-motion: reduce)`

for motion-heavy interactions.

## Keyboard focus

Focus-visible coverage is too sparse.

Every interactive element must have a visible keyboard focus state.

## Interactive card rows

Existing card expansion patterns include mouse-driven elements that are not consistently keyboard accessible.

Required:

- semantic button/control where appropriate
- keyboard activation
- correct focus
- correct `aria-expanded`
- no contradictory `aria-hidden` + interactive button state

## Live updates

Polled dashboard values should use a consolidated accessible status/live region rather than many independent announcements.

## Skip navigation

Add a skip link and proper main landmark target.

---

# 13. UX/UI — collapse/chevron component defect

There are currently multiple implementations of the same expand/collapse concept.

### Current implementations

1. Calendar `.expand-button + .chev`
2. History/Signals/Calendar date-toggle chevrons
3. Tools `.collapse-chev`
4. Material-specific special-case styling

### Confirmed visual defect

Some implementations rotate both:

- the container
- the child glyph

This creates the stacked/double-chevron appearance visible in the audit.

### Required fix

Create **one canonical ExpandableControl/Chevron primitive**.

Rules:

- one shared component contract
- one glyph
- rotate glyph only
- consistent size
- style-specific shape token
- consistent hover/focus/pressed state
- consistent accessibility semantics

Do not fix Calendar, History and Tools independently.

---

# 14. UX/UI — dark-mode parity

Some dark-theme rules exist only in `styles.css`, while later sheets introduce color changes without equivalent dark variants.

### Required fix

Dark mode must be a token/theme concern.

Do not create page-specific dark-mode patches.

---

# 15. UX/UI — theme-color metadata

The browser `theme-color` currently does not fully follow the active theme.

### Required fix

Update it when theme changes.

Also remove stale comments/documentation referring only to old Modern/Neo behavior.

---

# 16. UX/UI — static asset delivery

Previous audit found a dangerous deployment failure mode:

A CSS file referenced by HTML can return 404 if it is not registered in the server's static-file map.

### Required fix

Whenever a new frontend asset is added:

1. register it in the server file map
2. verify HTTP 200
3. verify cache/version behavior
4. only then reference it from HTML

Add an automated test where practical.

---

# 17. UX/UI architecture direction

## Correct hierarchy

We are **not** making three independent dashboards.

We are building one product with one foundation:

```
Frozen MULTIBOT2 architecture
        ↓
UX foundation
        ↓
Material 3 design foundation
        ↓
Canonical design tokens
        ↓
Canonical components
        ↓
Responsive layout system
        ↓
Theme adapters
   ┌────┼────┐
   ↓    ↓    ↓
 M3  Modern Neo
        ↓
      Pages
        ↓
 State / accessibility / responsive audit
```

### Important

Material 3 is the **foundation/reference system**, not a page-specific skin.

Modern and Neo-Brutalism must reuse the same:

- DOM
- components
- spacing contract
- interaction contract
- accessibility contract
- semantic tokens
- data/state model

Only their visual language changes.

---

# 18. UX/UI Pro Max + Jakub Krehel Skills methodology

Use these skills as the **review methodology**, not as a replacement for the MULTIBOT2 design system.

### Review order

1. Accessibility
2. Layout
3. Information hierarchy
4. Writing/content clarity
5. Typography
6. Color/contrast
7. Components
8. Interaction states
9. Responsive behavior
10. Visual polish

### Core rule

**Evidence before styling.**

Every significant finding should identify:

- symptom
- root cause
- affected component/page
- severity
- systemic fix
- verification method

### Systemic over local

Prefer:

`fix token/component once → all pages improve`

over:

`patch page A → patch page B → patch page C`

### State coverage

Every important component must be reviewed in:

- default
- hover
- focus
- pressed
- disabled
- loading
- empty
- success
- warning
- error
- long-content
- mobile
- narrow viewport
- reduced-motion mode

---

# 19. Dashboard-specific UX priorities

The trading dashboard is data-dense.

The hierarchy must be:

### Primary

- current actionable signal
- direction
- entry
- stop
- target
- freshness
- lifecycle state

### Secondary

- strategy
- asset
- timeframe
- timestamp
- account

### Tertiary

- diagnostics
- metadata
- delivery history
- scan details

Do not let decorative styling compete with actionable trading information.

---

# 20. Error UX contract

Errors must be understandable without exposing implementation noise unnecessarily.

For market-data failures:

### Dashboard

Show:

- affected strategy
- affected asset
- market-data status
- timestamp
- retry/backoff state
- whether trading is blocked for that asset

### Telegram

Do **not** repeatedly spam the same scan error.

If an operator-facing alert is needed, make it:

- deduplicated
- actionable
- bounded
- clear that paper mode remains active

### Logs

Keep full technical diagnostics in logs.

---

# 21. Master implementation order

## Phase 0 — Freeze

- Read authoritative API/rules/theme docs.
- Freeze trading/backend architecture.
- Capture current test baseline.
- Capture dashboard API fixture.
- Capture UI baseline for all 30 theme combinations.

## Phase 1 — Production incident

Fix/verify:

1. identify invalid market-data source
2. protect scan notification from repeated MARKET_DATA_ERROR spam
3. regression tests
4. verify paper mode remains active

## Phase 2 — Backend audit defects

1. Backtest account/risk fidelity
2. Supabase fallback semantics
3. candle-validation ownership
4. stale documentation

## Phase 3 — Design foundation

1. canonical tokens
2. cascade cleanup
3. shape system
4. typography
5. semantic colors
6. theme matrix

## Phase 4 — Canonical components

1. buttons
2. cards
3. inputs/selectors
4. badges/chips
5. tables
6. metric tiles
7. signal cards
8. alerts/errors
9. expandable controls
10. navigation

## Phase 5 — Accessibility

1. keyboard
2. focus
3. reduced motion
4. live regions
5. skip link
6. target sizes
7. contrast
8. screen-reader semantics

## Phase 6 — Page composition

Order:

1. Overview
2. Signals
3. History
4. Calendar
5. Tools
6. Backtest
7. Settings/appearance

## Phase 7 — Theme layers

Only after foundation/components are stable:

- Material 3
- Modern
- Neo-Brutalism

## Phase 8 — Final audit

Test:

- 30 theme combinations
- light/dark
- desktop/mobile
- keyboard
- long data
- errors
- empty states
- loading
- reduced motion
- API contract
- full pytest/CI

---

# 22. Acceptance criteria

The work is not complete until:

- [ ] No confirmed P0/P1 runtime defects remain.
- [ ] sweep_v2 market-data incident is understood and protected against repeat notification spam.
- [ ] Invalid OHLC data is still rejected.
- [ ] Backtest respects selected account risk/capital.
- [ ] Public API deployment boundary is documented/protected.
- [ ] Documentation agrees on the 25-asset current contract.
- [ ] One canonical design token system exists.
- [ ] CSS cascade is predictable.
- [ ] No unnecessary `!important` war remains.
- [ ] One canonical expand/collapse component exists.
- [ ] No overlap/clipping at supported viewports.
- [ ] All 30 style/accent/theme combinations work.
- [ ] Keyboard navigation works.
- [ ] Focus states are visible.
- [ ] Reduced-motion is respected.
- [ ] Error/empty/loading states are intentionally designed.
- [ ] Server truth is never recomputed by the UI.
- [ ] Trading logic is unchanged unless a confirmed defect is explicitly approved.
- [ ] Full automated test suite remains green.
- [ ] Final visual/UX audit is evidence-based.

---

# 23. Golden rule

> **Do not make MULTIBOT2 look fixed. Make MULTIBOT2 structurally correct so the same class of problem cannot return on the next page, theme, viewport, strategy, or release.**

That is the standard for the next implementation pass.
