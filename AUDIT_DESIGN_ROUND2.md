# Dashboard design audit — round 2

**Scope:** read-only. No source file was modified. Measured live on the running dashboard
(`http://localhost:3000/dashboard`, 390×844 device profile) across all five pages, plus a
read of `foundation.css` / `styles.css` / `appearance-overrides.css` / `app.js`.

**What is already good:** every expandable control is exactly 40×40 with the same radius
(the round-1 geometry fix held), all five pages are free of horizontal overflow, the nav works,
the bot is untouched and still scanning (`checked=25, errors=0`), 141 tests pass.

Seven problems remain. Six are real defects; the seventh is taste (type scale).

---

## 1. The chevron does not rotate — root cause found

`foundation.css:3417` opens the chevron with this rule:

```css
.collapse-control.is-open::after,
.collapse-control[aria-expanded="true"]::after,
.is-open > .collapse-control::after,
.is-open .collapse-control::after,          /* <-- too broad */
[aria-expanded="true"] > .collapse-control::after { transform: translateY(2px) rotate(-135deg) }
```

`.is-open .collapse-control::after` is a **descendant** selector (no `>`), so it matches *any*
chevron anywhere inside an expanded container — not just the one that belongs to it. When a
day group on Signals or Calendar is expanded, `section.signal-date-group.is-open` makes every
per-row chevron inside it render the "open" glyph permanently.

**Measured — 13 controls are stuck in the open glyph while reporting collapsed:**

| Page | Controls | Own state | Rendered glyph |
|---|---|---|---|
| Signals | 6 per-signal chevrons | `aria-expanded="false"` | up (open) |
| Calendar | 7 per-event chevrons | `aria-expanded="false"` | up (open) |

Clicking them changes nothing visually, because the ancestor decides the glyph. The date-group
headers and the Tools section headers rotate correctly — they are direct children or carry their
own state.

**Fix:** delete that one selector. The remaining four selectors already cover every real case —
verified: every control in the app either carries its own `is-open` class or has a synchronised
`aria-expanded` (date toggles, Tools controls, per-card expand buttons all confirmed).

---

## 2. Square panels next to rounded ones

Nine different corner radii are live on painted surfaces, but the contract only defines three
(14 outer / 11 inner / 10 control):

| radius | surfaces | where |
|---|---|---|
| **0** | **24** | the grey gutters and the rows inside them |
| 4 | 5 | chips |
| 7 | 2 | small badges |
| 9 | 3 | misc |
| 10 | 27 | controls |
| 11 | 34 | inner surfaces |
| 14 | 18 | cards |
| 50 / 999 | 11 | pills |

The square ones are precisely the grey gutters: `.tool-body` (r=0, ×5),
`history .history-summary-grid` (r=0), `calendar .calendar-summary-grid` (r=0), plus the white
rows inside them (`.asset-category`, `article.`, `span.`, `.compact-metric` — all r=0).

So the nest reads: rounded white card (14) → **square** grey band (0) → rounded grey panel (11)
→ **square** grey row (0). The grey fill's square corners sit against a rounded parent — that is
the "square borders with rounded grey fill" you are seeing.

**Fix:** one rule naming every painted surface, mapping each to the outer/inner token. Retire 0,
4, 7, 9, 50.

---

## 3. Grey boundary on grey background

The whole dashboard only has **two neutrals**: white (75 uses) and `#f1f3f6` (66 uses), plus a
page background of `#f6f7f9`. Three neutrals inside ~4% luminance of each other, so nesting
collapses into grey-on-grey and only the 1px borders separate anything.

**Nine grey-on-grey chains, all on Tools:**

```
.tool-body            (grey, r=0)          <- square
 └ .universe-grid     (grey, r=11, same)   <- rounded, same colour
    └ .asset-category (grey, r=0,  same)   <- square, same colour
```

Same pattern for `.backtest-controls`, `.rule-list`, `#accountsGrid`, `.diagnostic-grid`,
`.schedule-inline`. Home, Signals and History now do white → grey → white correctly — which is
exactly why Tools looks wrong.

**Fix:** strict alternation (tint → white → tint); drop the fill from the innermost row
containers so only one grey level is visible at a time.

---

## 4. The expansion buttons are too big for their rows

The control is the right size relative to *itself* (uniform 40×40 everywhere) but too large
relative to the box it sits in:

| Context | Control | Container | Share |
|---|---|---|---|
| Tools section header | 40px | 59–63px | 64% |
| History date header | 40px | 56px | 71% |
| **Signals / Calendar / Home per-card** | **40px** | **40px row inside a 56–63px card** | **100%** |

A 40px bordered grey tile that fills its row and is two-thirds of the card height reads as a
button competing with the content instead of a quiet affordance.

**Recommended:** 40 → **32px**, icon 9 → 7px, stroke 2 → 1.75px, and keep a **44px invisible tap
target** via a `::before` hit area so touch accessibility does not regress. Result: 57% of a date
header (12px clearance instead of 8px) and ~55% of a card.

---

## 5. Legend / label text fails accessibility contrast

19 distinct text roles fail WCAG AA under real alpha-composited measurement. The single biggest
cause is that the accent colour is used both as small text and as the fill of solid buttons.

| Text | Colour | Contrast | Needs |
|---|---|---|---|
| Eyebrows: `COMMAND CENTER`, `SIGNAL LEDGER`, `BY DATE`, `APPEARANCE` | `#059669` on `#f6f7f9` | **3.52:1** | 4.5 |
| Links: `View rules →`, `View all →`, `Forex Factory ↗`, `MULTIBOT` | `#059669` on white | **3.77:1** | 4.5 |
| **`Run backtest` (primary CTA), active `Light` chip** | white on `#059669` | **3.77:1** | 4.5 |
| `BUY` pill | `#059669` on tinted green | **3.26:1** | 4.5 |
| Date-group subtitle `6 signals · 6 BUY · 0 SELL` | `#64748b` on tinted row | **4.03:1** | 4.5 |
| Muted meta on the grey gutter (`14 days`, `CACHED`, `28 Sept 2026`) | `#64748b` on `#f1f3f6` | **4.28:1** | 4.5 |

**Fix:** a darker accent token for text and solid fills (emerald-700 class, ~5:1), and one step
darker muted neutral. Token values only — no restyle.

---

## 6. The accent picker lies in Neo style

| Style + accent | `--accent` resolves to | chip says |
|---|---|---|
| modern \| emerald | `#10b981` ✅ | Emerald |
| material3 \| emerald | `#006c4c` ✅ | Emerald |
| **neo \| emerald** | **`#ff5d1f` (orange)** ❌ | Emerald, pressed |
| every other combination | correct ✅ | ✅ |

**Fix:** one missing entry in the Neo accent map.

---

## 7. Typography drift (cosmetic)

15 distinct font sizes — `8.5, 9, 9.16667, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15, 22px`
— across 35 size/weight combinations. `9.16667px` and `13.5px` are rem-math drift, not design.

**Fix:** snap to a 6-step scale (9.5 / 10.5 / 11.5 / 12.5 / 14 / 22). Rounding only.

---

## Suggested fix order (one pass, CSS + one token only)

1. Chevron rotation — delete one selector in `foundation.css`.
2. Surface radius contract — every painted surface to the outer/inner token.
3. Grey-on-grey — alternate tint/white, drop the innermost fill.
4. Controls 40 → 32px with a preserved 44px tap target.
5. Accent/neutral contrast tokens + Neo emerald accent entry.
6. Type scale snap.

Items 1–3 are the visual inconsistencies you described; 4 is the button size; 5–6 are the
legibility and polish layer. No markup, JS, bot or data-contract changes are needed.
