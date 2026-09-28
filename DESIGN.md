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

The contract is active. Existing collapsible controls are migrated to it; future controls must use the same class and tokens.

## Surface contract

The canonical file ownership table above only holds if exactly one layer declares the
shape values. `appearance-overrides.css` currently carries the winning tokens, so it
must not re-declare its own literals — it points at the foundation contract:

| Token | Points at | modern | neo | material 3 |
|---|---|---|---|---|
| `--ui-outer-r` | `--f-outer-radius` → `--radius` | 14px | 10px | 16px |
| `--ui-inner-r` | `--f-inner-radius` → `--radius-sm` | 11px | 8px | 8px |
| `--ui-control-r` / `--ui-collapse-radius` | foundation control contract | 10px | 10px | 10px |

Style-specific outer/inner values come from the style's own `--radius*` tokens. That is
style identity, not drift. Any literal radius that is not one of the three tiers above is
a defect.

Surfaces alternate by nesting depth:

- outer card / workspace (one per section): `--surface`, `--ui-outer-r`
- body, gutter or panel inside that card: `--f-inner-bg` (which is `--surface-2`)
- content row, tile or control inside the gutter: `--surface`

A card may never be painted the same colour as the surface it sits on; the Tools
workspace and the Calendar established this language and Home, Signals and History
follow it.

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
