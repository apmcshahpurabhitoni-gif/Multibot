# MULTIBOT2 Dashboard Design Contract

## Purpose

This document is the stable UI contract for the MULTIBOT2 dashboard. It describes ownership and constraints; it is not a second CSS system.

## Engineering rule

Use the minimum change that satisfies the requirement. Preserve existing data flow, runtime behavior, APIs, trading logic, and page structure unless a UI contract explicitly requires a change.

## Foundation

Google Material 3 is the structural design-system reference.

The foundation owns:
- spacing
- sizing
- responsive geometry
- shape
- control dimensions
- navigation clearance
- interaction geometry
- accessibility-safe control targets

Themes must not redefine structural geometry unnecessarily.

## Canonical file ownership

| File | Responsibility |
|---|---|
| DESIGN.md | UI/design contract |
| foundation.css | canonical geometry and tokens |
| styles.css | component and page layout |
| appearance-overrides.css | visual theme appearance |
| appearance.js | theme/style/accent state |
| dashboard.html | semantic structure |
| app.js | dashboard UI rendering and interaction |
| dashboard-live-wiring.js | dynamic presentation wiring |
| tests/test_dashboard_ui.py | regression protection |

## ExpandableControl contract

All collapsible UI will converge on one control contract:
- 40px × 40px target
- squarish rounded rectangle, not circular
- 10px foundation radius
- one border
- one chevron
- closed state points down
- open state points up
- only the chevron rotates
- the container never rotates
- semantic button where the control is interactive
- aria-expanded reflects state
- reduced-motion must be respected

Pass 1 defines these tokens. Pass 2 migrates existing controls to them.

## App shell

The bottom navigation is a global occupied region. Pages must not require individual padding hacks to avoid being hidden behind it.

## Themes

Material 3, Modern, and Neo are appearance variants over the same component and interaction contracts.

Light/dark and accent choices must not create parallel geometry systems.

## Protected behavior

UI work must not alter:
- signal generation
- strategy logic
- trading/backtest logic
- database contracts
- API contracts
- Telegram delivery
- runtime scheduling
- market-data behavior

## Validation

Every migration must preserve:
- page loading
- data rendering
- responsive behavior
- existing interactions
- accessibility
- no horizontal overflow

Playwright/browser validation and visual review are applied after structural migration.
