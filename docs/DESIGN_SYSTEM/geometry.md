# Geometry — MULTIBOT2 Design System

Extracted from `styles.css`, `foundation.css`, `appearance-overrides.css` at v3.3.0.
Companion to [`../THEME_SYSTEM.md`](../THEME_SYSTEM.md), which owns colour and shape tiers.

---

## 1. Spacing scale

One scale, declared once in `:root`. Do not invent a value outside it.

| Token | Value | Typical use |
|---|---|---|
| `--space-1` | 5px | hairline gaps, icon padding |
| `--space-2` | 8px | inside compact chips, badge padding |
| `--space-3` | 11px | inside controls, button padding |
| `--space-4` | 14px | card padding (`--card-pad`), standard gutter |
| `--space-5` | 18px | section internals |
| `--grid-gap` | 7px | between grid tiles |
| `--section-gap` | 10px (**14px in neo**) | between stacked sections |

Neo widens `--section-gap` to 14px. That is **style identity, not drift** — Neo reads
airier and must not be normalised away.

## 2. Radius tiers — exactly three

| Tier | Token | Modern | Neo | Material 3 |
|---|---|---|---|---|
| Outer | `--radius` / `--ui-outer-r` | 14px | 10px | 16px |
| Inner | `--radius-sm` / `--ui-inner-r` | 11px | 8px | 8px |
| Control | `--ui-control-r` / `--ui-collapse-radius` | 10px | 10px | 10px |

Plus `--radius-xs` (9px / 6px / 4px) for inline chips, and **full pills** (`999px`)
reserved for pills, colour swatches and status dots. Any other literal radius is a
defect. Material 3 additionally exposes a five-step scale internally
(`--m3-radius-xs/sm/md/lg/xl/full`) but only the three tiers above are consumed by
components.

## 3. Border and depth

| Token | Modern | Neo | Material 3 |
|---|---|---|---|
| `--border-w` | 1px | **2px** | 1px |
| `--shadow` | `0 18px 44px rgba(15,23,42,.09)` | **`3px 3px 0 var(--line-strong)`** | `--m3-elevation-2` |
| `--shadow-soft` | `0 4px 16px rgba(15,23,42,.06)` | **`2px 2px 0 var(--line-strong)`** | `--m3-elevation-1` |

Neo shadows are **hard offsets with no blur** and resolve against `--line-strong`
(near-black in light, near-white in dark). Removing the blur changes Neo's entire
character — it is the single most style-defining value in the system.

## 4. Control sizes

`--control-height: 36px` is the standard. Verified sizes in use:
`20 · 24 · 26 · 27 · 28 · 29 · 30 · 31 · 32 · 34 · 36 · 38 · 40 · 42 · 44 · 45 · 46 · 48 · 50 · 52 · 54 · 56 · 58 · 64 · 90 · 124 · 132 · 180`

Rules:
- **No interactive target below 24px.** All 44 interactive controls measure
  **32×32** at desktop; the ExpandableControl contract is 40×40.
- Values above 90px are containers (cards, panels), not controls.
- Widths of 124/132/180 are fixed-width columns (nav rail is `--nav-w: 188px`).

## 5. Navigation and app shell

- Desktop rail: `--nav-w: 188px`, fixed left.
- Mobile: bottom navigation, a **global occupied region**.
  Content must reserve **76px** bottom padding so nothing hides behind it.
- **Never patch a page's padding to clear the nav.** The shell reserves the space.

## 6. Breakpoints

The CSS is mobile-first; almost every rule sits inside a `max-width` query.

| Query | Uses | Purpose |
|---|---|---|
| `max-width: 900px` | 5 | first collapse of the desktop rail |
| `max-width: 760px` | 14 | mobile layout switch |
| `max-width: 680px` | 1 | narrow adjustment |
| `max-width: 560px` | 71 | the dominant phone contract |
| `max-width: 430px` | 3 | small phone |
| `max-width: 400px` | 3 | small phone |
| `max-width: 390px` | 3 | iPhone-class |
| `min-width: 761px` | 3 | desktop-only |
| `min-width: 561px` | 1 | tablet |
| `min-width: 400px and max-width: 560px` | 1 | combined band |
| `prefers-reduced-motion: reduce` | 2 | motion off |

> **Lesson encoded here.** A missing closing brace on the `max-width:560px` query
> silently swallowed ~200 lines of shared geometry — the canonical
> `.collapse-control` and date-group rules — so phones looked right (the smaller
> queries re-supplied the geometry) while desktop rendered an empty `14x4` box.
> **Balance the braces and re-measure at desktop after every media-query edit.**
> `tests/test_frontend_syntax.py` and `tests/test_dashboard_ui.py` now guard this.

## 7. Surfaces alternate by nesting depth

```
depth 0  section / workspace  →  --surface      + --ui-outer-r
depth 1  gutter / panel       →  --f-inner-bg   (== --surface-2)
depth 2  row / tile / control →  --surface
```

**A card may never be painted the same colour as the surface it sits on.** Tools and
Calendar established this language; Home, Signals and History follow it.

## 8. Verification

Measure at **1440×900** and **390×844**. Both must show zero horizontal overflow and
zero targets under 24px. See [`validation.md`](validation.md).
