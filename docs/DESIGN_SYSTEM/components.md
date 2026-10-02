# Components — MULTIBOT2 Design System

Component inventory extracted from the shipped stylesheets at v3.3.0
(~124 distinct classes). Grouped by function, with the states and accessibility
contract each one must satisfy.

---

## 1. Shell and navigation
`app` · `topbar` · `brand` `brand-mark` `brand-copy` · `header-meta` `version-badge` ·
`desktop-nav` `nav-button` · `mobile-nav` · `page` `page-heading`

| Rule | Detail |
|---|---|
| Pages | Exactly one `.page` is `.active`; the rest are `display:none`. This is what guarantees **exactly one `<h1>`** in the accessibility tree. |
| Nav | Desktop rail `--nav-w: 188px`; mobile bottom nav is a globally occupied region requiring **76px** content clearance. |
| Pages | `overview`, `signals`, `history`, `calendar`, `tools`. |

## 2. Buttons and controls
`primary-button` `secondary-button` `text-button` `icon-button` `chip-option` ·
`filter-button` `theme-toggle` `trade-detail-button` `drawer-close`

| Rule | Detail |
|---|---|
| `type` | **Every** `<button>` needs `type="button"` or it submits its form. |
| Size | No interactive target below 24px; interactive controls measure 32×32, ExpandableControl is 40×40. |
| Focus | Never remove the focus ring. `.app{outline:0}` is safe **only** because `.app` is a non-interactive `div`. |

## 3. Surfaces and cards
`section-block` `workspace-heading` `workspace-count` `card-main` `card-state` ·
`chart-card` `tool-collapse` · `drawer-shell`

Surfaces alternate by nesting depth — see [`geometry.md`](geometry.md) §7.
**A card may never be painted the same colour as the surface it sits on.**

### Card row — keyboard contract (fixed at v3.3.x)
`.card-main` is a composite control:
- `role="button"` `tabindex="0"` `aria-expanded` `aria-label`
- Enter and Space toggle; the handler re-finds the row after re-render and
  restores focus, because `innerHTML` rendering destroys it
- The inner `.expand-button` is `tabindex="-1"` `aria-hidden="true"` — one tab
  stop per card, not two

## 4. Expandable / disclosure
`collapse-control` `expand-button` `tool-collapse` `signal-date-group` `history-date-group`

One contract for every disclosure — see [`../THEME_SYSTEM.md`](../THEME_SYSTEM.md) §6:
40×40 target · squarish rounded rectangle · 10px radius · one border · one chevron ·
closed points down, open points up · **only the chevron rotates** · real `<button>` ·
`aria-expanded` reflects state · reduced-motion respected.

## 5. Data display
`metric-card` `metric-grid` `detail-grid` `trade-row` `live-trade-row` ·
`scan-history-row` `calendar-item` `equity-line` `equity-point` `chart-bar` ·
`backtest-trade-row` `backtest-metrics` `universe-grid` `account-grid`

| Rule | Detail |
|---|---|
| Money | Client-formatted, `₹` + `en-IN`, `tabular-nums` so digits do not jitter on the 30s poll. |
| Missing | `null`/`undefined`/non-finite render **em-dash `—`**, never `0` or blank. |
| Escaping | Every interpolated value passes through `escapeHtml()`. |
| Sorting | `directional`/`fresh`/`stale` are **computed by the server**. Never recompute. |

## 6. Status and direction
`status-badge` `signal-side` `fresh` `stale` `trade-status` `impact-pill` ·
`news-dot` `positive` `negative` `direction-icon` `live-open-badge` · `clock`

- **State is never colour alone.** `.fresh`/`.stale`/`.buy`/`.sell` each carry text.
- **Direction has a shape** (▲/▼) as well as a colour, for users who cannot see colour.
- `clock` uses `tabular-nums` — it updates every second.

## 7. Overlays
`drawer` `drawer-price-grid` `drawer-status` · `release-modal` `release-modal-card`

- Opens, moves focus inside, closes on **Escape** and on the close button.
- Must return focus to the trigger on close.
- `connection-banner` uses `role="alert"` (assertive).

## 8. Appearance controls
`settings-group` `settings-row` `settings-label` `settings-inline` `settings-toggle` ·
`appearance-style-grid` `appearance-option` `appearance-swatch` · `chip-option`

See [`../THEME_SYSTEM.md`](../THEME_SYSTEM.md) §5. State is `.active` +
`aria-pressed`, never colour alone. Accent swatches are decorative; the accessible
name comes from the adjacent text.

## 9. Feedback and status
`empty-state` `connection-banner` `backtest-status` `calendar-status` `reason` ·
`inline-status` `tool-runtime` `tool-tag` `schedule-inline` `rule-list`

| Element | Live-region role |
|---|---|
| `#backtestStatus` | `aria-live="polite" role="status"` (pre-existing) |
| `#connectionBanner` | `role="alert"` (pre-existing) |
| `#dashboardAnnouncer` | `role="status" aria-live="polite" aria-atomic="true"` (**added**) |

> **`#dashboardAnnouncer` consolidates 11 previously silent values into one calm
> sentence per poll.** Adding a live region per value would make a screen reader
> unusable — it would interrupt 11 times every 30 seconds.

## 10. Utilities
`sr-only` · `skip-link`

`.sr-only` is visually hidden but announced (used by the announcer).
`.skip-link` is hidden until focused, then pins to the viewport so the first Tab
reaches it.

## 11. What a rebuild must not do

- Add a component rule containing a hex literal or a `[data-style=…]` selector.
- Introduce a fourth radius tier.
- Animate a value that changes on the poll.
- Make a status colour-only.
- Add an interactive `<div>` without `role`, `tabindex` and key handling.
