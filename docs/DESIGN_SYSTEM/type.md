# Typography — MULTIBOT2 Design System

Extracted from the shipped stylesheets at v3.3.0.

---

## 1. Font stacks

```css
--font: "Inter","SF Pro Text","Segoe UI Variable",ui-sans-serif,system-ui,
        -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
        "Helvetica Neue",Arial,sans-serif;
--font-tnum: "SF Mono",ui-monospace,"Cascadia Mono","Segoe UI Mono",
             Menlo,Consolas,monospace;
```

`--font` is the UI stack. **`--font-tnum` is reserved for figures that must align
in a column** — never for prose.

## 2. Material 3 type scale

Material 3 declares its own nine-step scale, used by that style's component rules:

| Token | Size | Token | Size |
|---|---|---|---|
| `--m3-body-large` | 16px | `--m3-label-large` | 14px |
| `--m3-body-medium` | 14px | `--m3-label-medium` | 12px |
| `--m3-body-small` | 12px | `--m3-title-large` | 22px |
| `--m3-headline-small` | 24px | `--m3-title-medium` | 16px |
| `--m3-headline-large` | 32px | | |

Titles snap to **14px / 17px** in the shared sheets.

## 3. Sizes actually present in the CSS

The current stylesheets declare these pixel sizes:

```
8 · 8.5 · 8.7 · 9 · 9.5 · 10 · 10.5 · 11 · 11.5 · 12 · 12.5 ·
13 · 13.5 · 14 · 14.5 · 15 · 15.5 · 16 · 17 · 22  px
```

No `rem` declarations remain — the earlier fractional-rem drift was removed.

> **Known defect, do not reproduce.** The mid-range `10 / 11 / 12px`
> declarations dominate the design but sit in regions the current cascade can no
> longer reach, and the scale carries many adjacent steps (8.5, 8.7, 9, 9.5,
> 10.5…). It is inconsistent by construction.
>
> **A rebuild should define one clean scale** — for example
> `11 · 12 · 14 · 16 · 20 · 24 / 32px` — and use nothing else. Do not try to
> reproduce the current 20-value spread.

## 4. The sub-10px problem

`8px, 8.5px, 8.7px, 9px, 9.5px` exist in the current sheets. **Do not copy these.**
Anything below ~11px fails legibility in practice and, at that size, is also a
contrast problem because anti-aliasing eats the glyph strokes.

Minimum for a rebuild: **11px** for dense metadata, **12px** for secondary body,
**14px** for primary body.

## 5. Tabular figures — mandatory for money

Any value that can change in place must use `font-variant-numeric: tabular-nums`,
otherwise the number jitters as digits change on every 30-second poll.

Currently applied in 11 rules including `.metric-card strong` and `.clock strong`.

**Still missing (fix in a rebuild):**
- `.workspace-count` — e.g. "12 signals"
- `.inline-status` — e.g. "0 completed trades"

## 6. Weight

Weights in use: `600` (badges), `800` / `900` / `950` (labels, chips, buttons,
eyebrows). The system leans heavy — uppercase micro-labels at `900`/`950` with
`letter-spacing: .17em` are a deliberate signature (`.eyebrow`, `.hero-kicker`).

Do not introduce a 400-weight paragraph style; nothing in the product uses one.

## 7. Money and numbers

Formatting belongs to the client and is **not** free choice — see
[`../API.md`](../API.md) §12.

```js
inr(v)    // ₹ + en-IN, 0–2 fraction digits, non-finite → "—"
number(v, d) // en-IN, fixed decimals, non-finite → "—"
```

The **em-dash `—` convention is load-bearing**: `null`, `undefined` and non-finite
all render `—`, never `0`, `NaN`, or a blank cell.
