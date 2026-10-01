# Theme System Contract — MULTIBOT2

**Status:** authoritative. Derived from `styles.css` and `appearance.js` at
**v3.3.0**. Guarded by `tests/test_contrast_tokens.py`, `tests/test_appearance_system.py`
and `tests/test_api_contract.py`.

**Scope.** 3 interface styles × 5 accents × 2 themes = **30 combinations**.
All 30 must work. All 30 currently pass WCAG AA contrast.

---

## 1. The one idea that makes this system work

There are **two token layers**, and keeping them separate is the whole trick:

```
   STYLE DEFINES          →      COMPONENT CONSUMES
   ─────────────                 ──────────────────
   --bg, --surface,               color: var(--text)
   --surface-2, --text,           background: var(--surface-2)
   --accent, --positive …         border: 1px solid var(--line)
```

- **Layer 1 — style definitions.** Only `styles.css` defines these. Three
  blocks: `:root` (modern, light), `html[data-theme="dark"]`, and
  `html[data-style="neo"]` + its dark variant. Material 3 defines a private
  `--m3-*` set and then **maps it onto** the same names.
- **Layer 2 — shared semantic tokens.** Components reference *only* these
  names. A component rule containing a hex literal or a style-specific selector
  is a defect, because it cannot survive a style switch.

> **Verified invariant:** `styles.css` is the **only** sheet that declares
> contrast tokens. `foundation.css` (342 rules) and `appearance-overrides.css`
> (343 rules) contain **zero** redefinitions of `--positive`, `--negative`,
> `--warning`, `--accent`, `--on-accent` or the `--*-soft` washes. Keep it that
> way. A rebuild that lets a later sheet redefine a contrast token silently
> breaks contrast in exactly one style/accent/theme combination.

### Three accent axes, one attribute each

```html
<html lang="en" data-theme="light" data-style="modern" data-accent="emerald">
```

| Attribute | Values | Meaning |
|---|---|---|
| `data-theme` | `light` \| `dark` | Colour scheme |
| `data-style` | `modern` \| `material3` \| `neo` | Interface language |
| `data-accent` | `emerald` \| `indigo` \| `amber` \| `rose` \| `cyan` | Brand hue |

**30 combinations** = 3 × 5 × 2. `neo` is *also* the default accent hue
(`--accent: #ff5d1f` orange) until an accent is chosen — a Neo quirk, not a bug.

---

## 2. Layer 1 — the shared token vocabulary

A rebuild must define every name below. Omitting one breaks components silently.

### Surface and ink
| Token | Role |
|---|---|
| `--bg` | App background, behind everything |
| `--surface` | Card / workspace fill |
| `--surface-2` | Body, gutter or panel nested inside a card |
| `--surface-3` | Third nesting level |
| `--text` | Primary ink |
| `--text-soft` | Secondary ink |
| `--muted` | De-emphasised ink (metadata, hints) |
| `--line` | Default hairline border |
| `--line-strong` | Emphasised border (Neo uses it as a full-strength edge) |

### Semantic status — the contrast-critical set
| Token | Role | Must contrast against |
|---|---|---|
| `--positive` | Gains, BUY-side, health OK | `--surface`, `--surface-2`, `--positive-soft` |
| `--negative` | Losses, SELL-side | same |
| `--warning` | Stale, degraded, partial | same |
| `--positive-soft` | Wash behind a positive element | `--positive` |
| `--negative-soft` | Wash behind a negative element | `--negative` |
| `--warning-soft` | Wash behind a warning element | `--warning` |

> **Known test gap.** `tests/test_contrast_tokens.py` composites washes over
> `--surface` only. Washes also paint on `--surface-2` (reachable via
> `.card-main:hover{background:var(--surface-2)}`). A rebuild should composite
> **every wash against both surfaces**, plus `--surface-3`.

### Accent
| Token | Role |
|---|---|
| `--accent` | Accent for text/borders/icons |
| `--accent-strong` | Accent for hover/active and high-emphasis text |
| `--accent-fill` | Solid accent **background** — pairs with `--on-accent` |
| `--on-accent` | Ink drawn **on top of** `--accent-fill` |
| `--accent-soft` | Accent wash |
| `--accent-softer` | Fainter accent wash |

> `--accent-fill` and `--accent` are frequently **different colours**. Rose light
> is the clearest case: `--accent:#f43f5e` but `--accent-fill:#e11d48`. Anything
> painting a filled button must read `--accent-fill`, never `--accent`.

### Shape, depth and metrics
| Token | Role |
|---|---|
| `--radius`, `--radius-sm`, `--radius-xs` | Outer / inner / control tiers |
| `--border-w` | Border weight |
| `--shadow`, `--shadow-soft` | Elevation |
| `--control-height` | Standard control height |
| `--nav-w` | Desktop nav width |
| `--space-1…5`, `--section-gap`, `--grid-gap`, `--card-pad` | Spacing |
| `--font`, `--font-tnum` | UI stack; monospace stack for tabular figures |
| `--color-scheme` (`color-scheme`) | Native control rendering |

### Style-owned namespace
| Token family | Owner | Role |
|---|---|---|
| `--m3-*` | material3 only | Full Material 3 role set + radius + elevation + type |
| `--ui-outer-r`, `--ui-inner-r`, `--ui-control-r`, `--ui-collapse-radius` | `appearance-overrides.css` | Effective shape contract; see §6 |
| `--f-*` | `foundation.css` | Foundation geometry (`--f-inner-bg` is `--surface-2`) |

---

## 3. Style definitions

### Modern — literal values in `:root`
The baseline. Light `:root` and `html[data-theme="dark"]` each list the full
vocabulary as literals. Radius `14/11/9`, border `1px`, soft blurred shadows.

`emerald` is the default accent and is **not** given its own block — it comes
from `:root` / the dark block. The other four are:
```css
html[data-accent="indigo"]{--accent:#6366f1;--accent-strong:#4f46e5;--accent-fill:#4f46e5;…}
html[data-accent="amber"]{--accent:#f59e0b;--accent-strong:#b45309;--accent-fill:#b45309;…}
html[data-accent="rose"]{--accent:#f43f5e;--accent-strong:#da1c45;--accent-fill:#e11d48;…}
html[data-accent="cyan"]{--accent:#06b6d4;--accent-strong:#0e7490;--accent-fill:#0e7490;…}
```
Dark accents are lighter: `indigo #818cf8`, `amber #fbbf24`, `rose #fb7185`,
`cyan #22d3ee`, each with a lighter `--accent-strong`.

### Material 3 — a private role set mapped onto the shared names
The only style that does **not** use literals directly. It declares ~50
`--m3-*` tokens, then binds:

```css
html[data-style="material3"]{
  --surface:var(--m3-surface);
  --surface-2:var(--m3-surface-container);
  --surface-3:var(--m3-surface-container-high);
  --bg:var(--m3-background);
  --text:var(--m3-on-surface);
  --text-soft:var(--m3-on-surface-variant);
  --muted:var(--m3-on-surface-variant);
  --line:var(--m3-outline-variant);
  --line-strong:var(--m3-outline);
  --accent:var(--m3-primary);
  --accent-strong:var(--m3-primary);
  --accent-fill:var(--m3-primary);
  --radius:var(--m3-radius-lg);      /* 16px */
  --radius-sm:var(--m3-radius-sm);   /* 8px  */
  --radius-xs:var(--m3-radius-xs);   /* 4px  */
  --shadow:var(--m3-elevation-2);
  --shadow-soft:var(--m3-elevation-1);
}
```

M3 role families to reproduce: `primary`, `secondary`, `tertiary`, `error`
(each with `-container` / `-on-*` pairs), `background`, `surface`,
`surface-variant`, `outline`, `inverse-*`, the five `surface-container-*`
elevation steps, `state-hover` / `state-focus` / `state-pressed`, six radii
(`xs…xl`, `full`) and four elevations.

M3 also carries its **own type scale** (`--m3-body-large 16px`, `body-medium 14`,
`body-small 12`, `label-large 14`, `label-medium 12`, `title-large 22`,
`title-medium 16`, `headline-small 24`, `headline-large 32`) and per-style
component overrides follow in the same sheet.

### Neo Brutalism — warm paper, hard offset shadows, 2px borders
Light: `--bg:#f3eee1`, `--surface:#fffcf4`, `--surface-2:#efe8d6`,
`--surface-3:#e2d8bf`, `--text:#141414`, `--line:rgba(20,20,20,.85)`,
`--line-strong:#141414`.

Signature traits a rebuild must keep:
- `--border-w: 2px` (double every other style)
- `--shadow: 3px 3px 0 var(--line-strong)` — **hard offset, no blur**;
  dark variant uses `3px 3px 0 #000`
- Radius collapses to `10/8/6`
- `--section-gap: 14px` (vs 10px elsewhere)

Neo is the only style whose **default accent** is orange (`#ff5d1f` light,
`#ff6a2b` dark) rather than emerald, and the only one that redefines
`--positive` / `--negative` / `--warning` in its style block
(`#096c42` / `#c81e3d` / `#7f5400` light).

---

## 4. The 30-combination matrix

Only these blocks exist. A rebuild needs the equivalent.

| Layer | Selector | Count |
|---|---|---|
| Base light | `:root` | 1 |
| Base dark | `[data-theme="dark"]` | 1 |
| Modern accents | `[data-accent="indigo\|amber\|rose\|cyan"]` (light + dark) | 8 |
| Neo light | `[data-style="neo"]` | 1 |
| Neo dark | `[data-theme="dark"][data-style="neo"]` | 1 |
| Neo accents light | `[data-style="neo"][data-accent=…]` × 5 | 5 |
| Neo accents dark | `[data-theme="dark"][data-style="neo"][data-accent=…]` × 5 | 5 |
| Neo light-only fixes | `[data-theme="light"][data-style="neo"][data-accent="indigo"\|"rose"]` | 2 |
| M3 light | `[data-style="material3"]` | 1 |
| M3 dark | `[data-theme="dark"][data-style="material3"]` | 1 |
| M3 accents light/dark | `[data-style="material3"][data-accent=…]` × 8 | 8 |

### Load-bearing rule — do not "simplify" these
```css
/* Light-only: these fills are too mid-luminance for the dark Neo on-accent.
   Scoped to [data-theme="light"] so the dark fills keep their dark on-accent. */
html[data-theme="light"][data-style="neo"][data-accent="indigo"]{--accent-fill:#6163ec;--on-accent:#ffffff}
html[data-theme="light"][data-style="neo"][data-accent="rose"]{--on-accent:#ffffff}
```

Scoping to `[data-theme="light"]` is **required**. Un-scoping these makes the
dark Neo indigo/rose accent carry `#ffffff` on a light fill and fail contrast.
This is exactly the kind of rule that must live in the theme documentation
rather than in a builder's memory.

### Values that exist for a reason (do not revert)
These were tuned to clear WCAG AA. Reverting any of them reintroduces a failure.

| Token | Was | Now | Why |
|---|---|---|---|
| `:root --positive` | `#047857` | `#037353` | 4.5:1 on `--surface` |
| neo `--warning` | `#946200` | `#7f5400` | light Neo needed more depth |
| neo `--positive` | `#0b7a4b` | `#096c42` | light Neo needed more depth |
| rose `--accent-strong` | `#e11d48` | `#da1c45` | dark rose wash |
| neo amber `--accent-strong` | `#d97706` | `#a05804` | light Neo amber |

---

## 5. `appearance.js` — state, persistence and ownership

`appearance.js` is a **presentation-only bridge** and the single owner of
style state. It runs as an IIFE, exports `window.applyStyle` and
`window.applyAccent`.

### Persistence
| Key | Values | Default |
|---|---|---|
| `mavis-style` | `modern` \| `material3` \| `neo` | `modern` |
| `mavis-theme` | `light` \| `dark` | `light` |
| `mavis-accent` | `emerald` \| `indigo` \| `amber` \| `rose` \| `cyan` | `emerald` |

`localStorage`. **Any invalid stored value silently falls back to the default**
via `validStyle()` / `validAccent()` — a rebuild must keep this tolerant, so a
user with stale storage is never stuck on a blank screen.

### Resolution order
```js
style  = valid(root.dataset.style      || storage.getItem("mavis-style"))  || "modern"
theme  = root.dataset.themePref || root.dataset.theme || storage.getItem("mavis-theme") || "light"
accent = valid(root.dataset.accent || storage.getItem("mavis-accent")) || "emerald"
```
`dataset` wins over storage so a server-rendered or scripted override works.
`themePref` is checked before `theme`; support both.

### Side effects of every change
`sync()` re-applies all three:
1. Sets `data-style`, `data-theme`, `data-accent` on `<html>`.
2. Toggles the legacy class trio — `modern-mode`, `material3-mode`,
   `neo-mode` — on `<html>` (exactly one is ever present).
3. Marks the matching chips: toggles `.active` and sets `aria-pressed="true|false"`
   on every `[data-style-choice]`, `[data-theme-choice]`, `[data-accent-choice]`.

### Ownership rule (a rebuild must preserve this)
`appearance.js` binds its click handlers in the **capture phase** and calls
`event.preventDefault()` **and** `event.stopImmediatePropagation()`. This exists
to suppress a legacy style listener in `app.js` that would otherwise perform a
second, conflicting write. It guards with `root.dataset.appearanceBound` /
`accentBound` so re-execution cannot double-bind.

A new UI has one style owner and no legacy listener — which means this
suppression shim is *removable*. If you keep `app.js` as-is, keep the shim.

### Chip markup contract
```html
<button class="chip-option" data-theme-choice="light" type="button">Light</button>
<button class="chip-option" data-style-choice="neo" type="button">Neo Brutalism</button>
<button class="chip-option" data-accent-choice="emerald" type="button"><i class="appearance-swatch" style="background:#10b981"></i>Emerald</button>
```

Three rules:
1. **Every chip needs `type="button"`.** Without it, a chip inside a form
   submits.
2. **Every chip must have an accessible name from its own text content.** The
   accent chips are named by their label ("Emerald"), with
   `<i class="appearance-swatch">` as a purely decorative colour sample. If a
   redesign drops the text and keeps only the swatch, an `aria-label` becomes
   mandatory or the control is unnamed.
3. **State is expressed with `.active` + `aria-pressed`, never colour alone.**
   `appearance.js` sets both.

The group wrapper is `<div class="settings-inline" aria-label="Accent color">`;
each row also carries a `<span class="settings-label">` visible label.

---

## 6. Shape contract

| Token | Modern | Neo | Material 3 |
|---|---|---|---|
| `--ui-outer-r` → `--radius` | 14px | 10px | 16px |
| `--ui-inner-r` → `--radius-sm` | 11px | 8px | 8px |
| `--ui-control-r` | 10px | 10px | 10px |

Exactly **three** radius tiers. Any literal radius outside these tiers, pills,
swatches and dots is a defect.

Surfaces alternate by nesting depth — **a card may never be painted the same
colour as the surface it sits on**:
```
depth 0  section  →  --surface,   --ui-outer-r
depth 1  gutter   →  --f-inner-bg (== --surface-2)
depth 2  row/tile →  --surface
```

### ExpandableControl contract (one control, everywhere)
40×40 target · squarish rounded rectangle, not circular · 10px radius · one
border · one chevron · closed points down, open points up · **only the chevron
rotates, the container never does** · semantic `<button>` ·
`aria-expanded` reflects state · reduced-motion respected.

---

## 7. Rules a new UI must not break

| Rule | Current status |
|---|---|
| **Zero** `transition: all` | Enforced; every transition names its property |
| Reduced-motion honoured | `@media (prefers-reduced-motion: reduce)` in all 3 sheets |
| `outline: 0` only on non-interactive | `.app{outline:0!important}` — a plain `div`, benign |
| **Exactly one** `<h1>` visible | Hidden pages are `display:none` |
| No horizontal overflow | Verified at 1440×900 and 390×844 |
| Interactive target ≥ 24px | All 44 controls are 32×32 at desktop |
| Money uses `tabular-nums` | `.metric-card strong`, `.clock strong`, 11 rules |
| Every button named; every input labelled | 0 violations |
| No `div` click handlers | Cards use real buttons |
| Radius confined to 3 tiers + pills/swatches/dots | — |
| One type scale across all styles | 11 sizes identical in all 3 styles |

### Two accessibility defects a rebuild should close
1. **Card bodies are mouse-only.** `.card-body`/`.card-main` is a `<div
   data-expand>` handled by a delegated click; it is not focusable and has no
   `role`. The sibling `.expand-button` *is* a real `<button>` with
   `aria-expanded`. Make the row itself focusable (`tabindex="0"`) with a key
   handler, or drop the div handler and rely on the button.
2. **11 polled values are silent to screen readers.** `systemStatus`,
   `versionBadge`, `overviewTotalPnl`, `overviewTradeCount`, `overviewSignalCount`,
   `scanSummary`, `signalsResultCount`, `historyResultCount`, `historyClosedCount`,
   `equityCurveValue`, `heroStatus` are updated by a 30 s poll with **no live
   region**. Only `backtestStatus` (`aria-live="polite" role="status"`) and
   `connectionBanner` (`role="alert"`) exist. Wrap a status summary in a polite
   region rather than 11 separate ones, or the screen reader becomes unusable.

---

## 8. Contrast contract

**WCAG 2.1 AA, normal text 4.5:1, large text and UI components 3:1.**

Current state: **0 failures** across 30 combinations × 2 viewports
(120 checks) after the v3.3.0 token corrections in §4.

Checked pairs: `--text`/`--text-soft`/`--muted` on `--bg`/`--surface`/
`--surface-2`/`--surface-3`; `--accent`/`--accent-strong`/`--positive`/
`--negative`/`--warning` on `--surface`/`--surface-2`; `--on-accent` on
`--accent-fill`; each `*-soft` wash against its base ink and against the
surface it paints on.

A rebuild inherits this obligation: **any new style, accent or theme must be
added to the contrast test in the same commit that introduces it.**

---

## 9. Rebuild guidance

Keep the two-layer split. Four files, strictly ordered, **no overrides**:

```css
/* 1. tokens.css    — pure variables, zero component rules, zero literals
                      outside the token definitions themselves */
@import "themes.css" layer(themes);

/* 2. base.css      — resets, typography, layout primitives, app shell */

/* 3. components.css — every component, referencing ONLY shared tokens */

/* 4. themes.css    — the 30 combinations, defining shared tokens only */
```

Rules:
- A component rule may **never** contain a hex literal or a
  `[data-style=…]`/`[data-accent=…]` selector.
- One layer declares a token's **value**; the others may only **re-declare it
  for a different style/theme/accent**. Never two layers setting the same
  selector.
- The existing 3-sheet cascade (`styles.css → foundation.css →
  appearance-overrides.css`) is a patch-on-patch artifact that `DESIGN.md`
  itself describes as partially unreachable past ~50 KB. **Do not reproduce
  it.** The rewrite above is the fix.