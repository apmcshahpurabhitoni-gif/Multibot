# MULTIBOT2 Dashboard — Consolidated UI/UX Audit

**Scope:** read-only audit, synthesised from three measurement passes on `c5657d3`.
**No source file was modified.**

**Method.** All values are live measurements taken on the running preview at
`http://localhost:3000`, at **390×844** and **1440×900**, light theme, `emerald`
accent, by clicking the real style chips (never by writing `dataset` directly)
and reading computed styles after the transition settled. Causal claims about the
cascade were confirmed by enumerating every CSSOM rule matching the element
(2,007 rules scanned), not inferred from source. Data claims were confirmed
against `GET /api/dashboard`.

**Confidence is stated per finding.** Seven claims carried in from earlier passes
did not survive measurement; they are listed in §6 rather than silently dropped.

---

## 1. Executive summary

The dashboard is in better shape than the three reports it has collected suggest.
**Contrast passes 100%. There is exactly one `h1`, zero heading-level skips, a
working skip link, correct landmarks, no horizontal overflow at either viewport,
correct timezone handling, and a real bottom-nav clearance.** Seven of the
"critical" claims from earlier passes were measurement errors and are refuted in
§6 — including "the Run backtest button is unreachable", "the page is truncated",
and "the clock is 3.5 hours wrong".

The genuine problems are **system-level, not component-level**, and they cluster
into four root causes:

1. **Accessibility contracts exist and are then overridden.** `aria-expanded` and
   `aria-label` are emitted correctly on every expandable — and every one of them
   also ships `aria-hidden="true"` and `tabindex="-1"`. The dialog sets
   `aria-modal="true"` and focuses its close button — and has no focus trap.
2. **The cascade is inverted.** `dashboard.html` loads `styles.css` →
   `foundation.css` → `appearance-overrides.css`. Foundation loads *after*
   styles, so style-level overrides cannot win. This is why Modern and Material 3
   read identically and why Neo's motion never applies.
3. **`appearance-overrides.css` fixes rules are style-blind.** `#page-tools …`
   rules at specificity (1,3,0) outrank `html[data-style="material3"] .x` at
   (0,2,1), silently re-imposing Modern geometry on Material 3 and Neo inside
   the page used most.
4. **The type scale is not a scale.** Ten font weights and 207 declarations under
   12px. Tokens exist (154 custom properties declared) and contrast is fine, but
   the type tokens are not consumed — which is why every new component invents
   its own size and every audit reports "inconsistency".

**Severity count:** 3 critical, 7 major, 6 minor, 7 confirmed-passing,
7 prior claims refuted.

**The single highest-value fix** is C1 — one helper in `app.js` makes every
expandable in the product unreachable by keyboard.

---

## 2. Critical findings

### C1 — Every expandable control is hidden from keyboard and screen readers

**Measured.** `26 of 26` `button.expand-button` carry `aria-hidden="true"` and
`tabindex="-1"` (counted across all pages at 1440×900; `10 of 10` on Tools alone).
Sampled box: `aria-hidden=true tabindex=-1` on every instance.

**Why it matters.** These are real `<button>` elements — pointer-clickable, with
correct `aria-expanded` and `aria-label`. But a keyboard user cannot Tab to them,
and a screen reader will not announce them. A keyboard user therefore **cannot
expand any signal card, trade card, calendar event, asset card or settings group
on any page.** There is no recovery path: unlike the modal (C2), there is no
Escape escape-hatch.

**Root cause.** One helper — `expandButton()` at `app.js:33` — emits all three
attributes, so every page inherits it.

**Fix.** Drop `tabindex="-1"` and `aria-hidden="true"` from the helper. Keep
`aria-expanded` / `aria-label`, which are already correct. One-line change, one
product-wide effect. Highest severity-to-effort ratio in the report.

---

### C2 — Release modal has no focus trap (WCAG 2.4.3 Focus Order)

**Measured.** Opening the dialog moves focus to `#releaseModalClose`. Walking the
document tab order from there:

```
Tab 1: OUTSIDE  A.brand                 Tab 5: OUTSIDE  BUTTON.nav-button.active
Tab 2: OUTSIDE  #whatsNewButton         Tab 6: OUTSIDE  BUTTON.nav-button
Tab 3: OUTSIDE  #refreshButton          Tab 7: OUTSIDE  BUTTON.nav-button
Tab 4: OUTSIDE  #themeToggle            Tab 8: OUTSIDE  BUTTON.nav-button
```

All eight stops land outside the dialog, despite `aria-modal="true"`.

**What already works — do not "fix" these.** `role="dialog"` and
`aria-modal="true"` are set; `openReleaseModal()` moves focus to the close
button; and **Escape does close the modal** — the handler is at `app.js:365`
(`document.addEventListener("keydown", … if (event.key === "Escape") …)`),
verified live (`open=true` → Escape → `open=false`).

**Why it still matters.** It is a focus-order failure, not a lockout: a keyboard
user can Tab out of the dialog into the page behind it and lose their place. The
prior report's framing ("a keyboard user has no way out") overstates it.

**Fix.** ~12 lines: cycle Tab/Shift+Tab within the modal's tabbable set and
return focus to the opener on close.

---

### C3 — Material 3 is a recolour, not a design system

**Measured across 32 sampled components.** Material 3 changes **colour,
elevation and corner radius**. It changes **no padding, no font size, no font
weight, no letter-spacing, no gap**, and — apart from the nav pill — **no
control size**.

| Property | Modern | Material 3 | Applied? |
|---|---|---|---|
| accent | `#10b981` | `#006c4c` | yes |
| card bg / border / radius | `#fff` / `rgba(…,.12)` / 11px | `#f3f6f3` / `#c0c9c3` / 8px | yes |
| card shadow | `0 4px 16px rgba(.06)` | `0 1px 2px + 0 1px 3px` | yes |
| `body` background | `#f6f7f9` | `#fafdf9` | yes (Δ ≈ 3/255, invisible) |
| nav-button | radius 11px, 1px border, 46px | radius **999px**, **0** border, 40px | yes — the only real shape change |
| **h1** | 22px / 700 / −0.77px | identical | **no** — M3 declares 32px / 600 / −.02em |
| **eyebrow** | 11px / 700 / 1.65px | colour only | **no** — weight 600 and `.08em` lost |
| **primary-button** | radius 10px, min-h 32px, pad 8px 14px | identical | **no** — M3 declares a pill, 40px, `0 20px` |
| **icon-button** | 32×32, radius 10px, 2px border | identical size | **no** — M3 declares 40×40, border 0 |
| **chip-option** | radius 10px, min-h 32px, 9.5px | identical | **no** — M3 declares a pill, 36px, 12px |

**Three causes, each confirmed by rule dump:**

1. **Style-unscoped `!important` in the last layer.**
   ```
   appearance-overrides.css:209  .page-heading h1 { font-size:22px!important; font-weight:700!important; letter-spacing:-.035em!important }
   appearance-overrides.css:210  .eyebrow         { font-size:11px!important; font-weight:700!important; letter-spacing:.15em!important }
   ```
   These outrank `html[data-style="material3"] .page-heading h1` (0,2,2) **and**
   `html[data-style="neo"]` at `styles.css:795`. Two rules flatten the type scale
   across all three styles.

2. **Style-blind `#page-tools` fixes.** Verified rule dump for `.chip-option`:
   ```
   styles.css                | html[data-style="material3"] .chip-option        { var(--m3-radius-full) }   ← (0,2,1)
   appearance-overrides.css  | #page-tools .tools-appearance .chip-option       { 10px }                     ← (1,3,0)  WINS
   ```
   Every `#page-tools` geometry rule re-imposes Modern geometry on Material 3
   *and* Neo.

3. **Inverted cascade in `dashboard.html`.** Load order is
   `styles.css?v=…` → `foundation.css?v=…` → `appearance-overrides.css?v=…`.
   The documented contract is foundation → styles → appearance. Foundation
   loading second means its geometry beats style-level geometry.

**Fix, cheapest first.** (a) Scope causes 1's two rules so Material 3 and Neo can
opt out — 2 edits, instantly restores the type-scale difference. (b) Scope or
counter the `#page-tools` block. (c) Reorder the stylesheets **last**, because it
invalidates the whole 60-rendering matrix and needs a full re-run.

---

## 3. Major findings

### M1 — The type scale is not a scale

**Measured.** Ten distinct `font-weight` values: 500, 550, 600, 650, 700, 750,
800, 850, 900, 950. **207 font-size declarations under 12px** across four sizes:
10px ×55, 10.5px ×61, 11px ×55, 11.5px ×35.

The product's primary status readout renders at **9.5px**:

```
hero-pills span   9.5px   "0 ACTIVE SIGNALS" / "25 ASSETS WATCHING" / "● SYSTEM ONLINE"
```

**Why it matters.** This is the root cause behind most "the UI feels
inconsistent" reports. The token layer genuinely exists — 154 custom properties
are declared and `--radius*` resolves correctly per style — but the *type* tokens
are not consumed, so each component invents its own size. This is a real
systemic finding, and prior reports understated it (they counted 7 weights and
"6 sizes under 12px"; the true counts are 9 weights and 207 declarations).

**Fix.** Snap to a 6-step scale. Every affected declaration sits in the
unreachable tails of `styles.css` / `foundation.css` documented in `DESIGN.md`
items 3/4, so it needs to be done in `appearance-overrides.css`. Guard every
replacement in `tests/test_visual_consistency_audit.py`.

---

### M2 — Neo Brutalism has borders and shadows but almost no animation

**Measured.** Neo declares `transition` in **zero** rules. Fifteen of seventeen
sampled selectors have byte-identical transition lists to Modern. Where Neo's own
hover/active rules change `transform` and `box-shadow`, the transition often does
not cover them:

| Control | Transition declares | Neo hover/active changes | Result |
|---|---|---|---|
| `.primary-button`, `.secondary-button` | `transform` + `box-shadow` ✓ | transform + shadow | **correct — reference case** |
| `.collapse-control` | `background, color, border-color` | **transform + box-shadow** | ❌ jumps, does not lift |
| `.nav-button` | `background, color, border-color` | **transform + box-shadow** | ❌ snaps on all 5 tabs |
| `.icon-button` | transform, bg, color, border | transform + **box-shadow** | ⚠️ half-animated |
| `.chip-option` | bg, border, color, transform | transform + **box-shadow** | ⚠️ half-animated |
| `.signal-date-toggle` | `transform .12s, box-shadow .12s, background .12s` | — | ✓ Neo re-timed this one |

**Why it matters.** The physics exist on 13 control classes (`translate(-1px,-1px)`
+ `3px 3px 0` on hover; `translate(3px,3px)` + `0 0 0` on active) — but on 3 of
13 the motion is instantaneous, so Neo feels inert exactly where it should feel
most tactile. `.signal-date-toggle` proves the intent was there; it reached one
control out of thirteen.

**Fix.** Add `transition` (or extend the existing lists) to cover `transform` and
`box-shadow` on `.collapse-control`, `.nav-button`, `.icon-button` and
`.chip-option`. Keep the existing reduced-motion contract.

---

### M3 — Neo's 2px border takes content width without returning padding

**Measured.** Neo changes **zero padding values** — all 19 sampled components are
byte-identical to Modern (`.metric-card 7px 10px`, `.section-block 14px`,
`.hero 10px 12px`, `.primary-button 5px 10px`, `.settings-field input 7px 11px 7px 23px`).

Because the border goes 1px → 2px on all four sides, Neo silently removes 4px
from every content box:

```
.section-block   366×325  →  363×327
.chart-card      336×247  →  331×247
.hero            366×162  →  366×165
```

One compensation is correct: `.section-block` margin `12px 0 0 0` →
`12px 3px 3px 0`, making room for the down-right shadow. **But `.tool-card`,
`.metric-card` and `.signal-card` receive the same 2px/3px hard shadow with no
such compensation**, so their shadows bleed into the neighbouring card's padding.

**Why it matters.** This reframes "reconsider Neo's padding". The padding is not
inconsistent — it was never given back. The visual result is "same padding, less
room", which is why Neo reads as *tighter* than Modern rather than bolder.

**Fix.** Return ~2px of padding on Neo bordered surfaces, and add the same
shadow-compensation margin to `.tool-card` / `.metric-card` / `.signal-card`
that `.section-block` already has.

---

### M4 — Neo misses borders and shadows on its largest surfaces

**Measured** (`border-width: 0`, `box-shadow: none` in *both* styles, i.e. Neo
contributes nothing): `.chart-card` — the equity-curve panel, the largest single
surface on Home — `.tool-body`, `.universe-grid`, `.workspace-heading`,
`.page-heading`, `.asset-category`, `.settings-rule`, `.signal-date-group`.

Separately, **`.status-badge` and `.chip-option` keep a 1px border** in Neo while
everything else is 2px — an inconsistency inside Neo itself.

**Fix.** Extend Neo's 2px + hard-shadow treatment to the list above, or make
`.chart-card` deliberately borderless and say so in `DESIGN.md`. Raise the two
1px holdouts to 2px.

---

### M5 — Home spends 41–44% of its height on three "no signals" sections

**Measured, section by section:**

| Section | @390 | @1440 | Content |
|---|---|---|---|
| `page-heading` | 43px | 43px | "Home" |
| `hero` | 162px | 122px | kicker + headline + 3 pills |
| `metric-grid four` | 89px | 40px | account value / P/L / trades / signals |
| `overview-equity` | 325px | 396px | equity chart (314px of chart) |
| `overview-risk` | 183px | 134px | 4 locked-limit metrics |
| **`overview-activity`** | **278px** | **396px** | signals-by-day chart, empty |
| **`overview-scan`** | **114px** | **78px** | one line of text |
| **`overview-signals`** | **214px** | **199px** | empty state (105px) |
| **page total** | **1493px** | **1520px** | |
| document | 1665px | 1654px | incl. shell chrome |

- @390: 278 + 114 + 214 = **606px of 1493px = 40.6%**
- @1440: 396 + 78 + 199 = **673px of 1520px = 44.3%**

**Why it matters.** Three consecutive sections all communicate "no fresh
signals", and they are the two largest sections on the page after the chart.
`.overview-scan` is **78px of card to carry one line of text** (40px heading +
40px block + 28px status). Meanwhile the Signals page holds 12 real records one
tap away.

**Fix.** When `fresh_directional === 0`, collapse the three into one compact
status row naming the count that *does* exist (see M6). Keep the equity chart
full size — that one carries real information.

---

### M6 — Empty-state copy is factually wrong

**Measured.** `GET /api/dashboard` returns:

```
counts = { signals: 500, directional_signals: 12, fresh_directional: 0, stale_directional: 12 }
```

Home renders **"No signal records — The latest completed scan found no approved
directional signal."** under a heading reading "Active Signals", beside a hero
pill reading **"0 ACTIVE SIGNALS"**.

**The numbers are correct; the words are not.** Fresh directional signals are
genuinely 0 and all 12 are stale (past the 1-hour gate). But the copy claims
there are no signal *records* — there are 500, and 12 are on the Signals page
right now. An earlier report called this a "0 vs 3 contradiction"; that reading
is wrong, and so is any plan to "fix the count". The count is right.

**Fix.** Reword to name the stale set — e.g. "No fresh signals · 12 older in the
ledger · View signals →". This is a copy fix, not a data fix, and it resolves the
perceived contradiction the earlier report saw.

---

### M7 — Decorative glyphs are exposed to assistive technology

**Measured.** **0 of 10** nav glyph spans carry `aria-hidden`. The glyphs are bare
Unicode characters — `◆` Signals, `◷` History, `◉` Calendar, `⚙` Tools — in a
plain `<span>`, across 10 nav buttons (5 pages × `.desktop-nav` + `.mobile-nav`).

**Why it matters.** A screen reader announces "black diamond", "white bullet",
"gear" *before* the label, on every navigation control, on every page.

**Fix.** Add `aria-hidden="true"` to each glyph span. Markup only, no CSS, no
layout risk. Cheapest accessibility win in the report alongside C1.

---

## 4. Minor findings

| # | Finding | Measured |
|---|---|---|
| **N1** | Mobile nav overlaps the `RISK CONTROL` heading at first paint | @390×844, `scrollY=0`: heading y 762–802, nav band y 777–837 → 20px of a 40px heading covered; 13 elements intersecting. Clears on scroll; at max scroll Active Signals sits y 537–752, fully clear of the nav top at 777. |
| **N2** | Hero pills wrap 2+1 on mobile | "SYSTEM ONLINE" occupies a full 266px row alone (container is 266px). One extra 28px row + gap. |
| **N3** | Dead hero markup ships to every client | `.hero p { display: none }` in `styles.css` — the tagline "Monitor markets, discover opportunities…" is in the DOM and never rendered. |
| **N4** | No footer landmark | `header=1 nav=2 main=1 footer=0`. |
| **N5** | No deep links | `setPage()` toggles `.page.active`; no `history.pushState`. `/tools` 404s; back button and reload lose position. |
| **N6** | Neo uses literal radii (8 / 10 / 7) instead of `--radius*` tokens | Tokens resolve correctly per style; the literals enter through the same style-blind `#page-tools` block as C3. |

---

## 5. Confirmed working — protect these

Re-verified independently in this pass. Do not regress them.

| Property | Result |
|---|---|
| **Contrast (normal text)** | **100% of probes pass 4.5:1** — hero pill 16.06:1, eyebrow 5.12:1, section note 5.44:1, metric label 5.44:1, metric sub-label 17.85:1, chart caption 4.89:1 |
| **Headings** | Exactly one visible `h1` ("Home"); zero level skips — sequence `1,2,2,2,2,2,2,2` |
| **Landmarks + skip link** | `header`/`nav`×2/`main` present; skip link → `#overview` works |
| **Horizontal overflow** | None at 390 or 1440 |
| **Timezone correctness** | `clock()` and `timestamp()` both pin `timeZone: CONFIG.timezone` (`Asia/Kolkata`). Measured simultaneously: clock `00:27:57`, calendar cache `05 Oct 2026, 00:22`, now `05 Oct 2026, 00:27` — 5 minutes apart, while the browser ran UTC 18:57. **Correct.** |
| **Bottom-nav clearance** | `.app` reserves `padding-bottom: 92px` for a 60px bar; `.mobile-nav` is a structural sibling of `main` inside `.app`. Documented as a deliberate consolidation in `appearance-overrides.css` §8. |
| **Loading states** | Skeletons ship (`@keyframes skeletonPulse`); zero console errors observed |

---

## 6. Prior claims that did not survive measurement

Recorded so they are not re-litigated or "fixed".

| Claim | Verdict | Evidence |
|---|---|---|
| "Run backtest button is unreachable / hidden behind the nav" | **False** | The Backtest card ships collapsed. Opened and scrolled to `maxScroll`: button y 377–413, nav y 777–837, overlap **0px**, and `elementFromPoint` at the button's centre returns the button itself. |
| "Page truncated at 1664px; History/Calendar/Tools inaccessible" | **False** | 4 of 5 `<section class="page">` are `display: none` and swapped by `setPage()`. 1665px was Home's correct document height. `/tools` is not a route, which is what produced the 404-shaped conclusion. |
| "Bottom nav occludes content; zero scroll clearance reserved" | **Mostly false** | Clearance exists on `.app` (92px), not on `body`/`main` — and the consolidation is deliberate (`appearance-overrides.css` §8). At max scroll Active Signals is fully clear by 25px. **Partly true:** see N1, the first-paint collision. |
| "Hero consumes ~50% of the first viewport" | **False** | Hero is 162px of a 1665px document = **9.7%** @390; 122px of 1654px = **7.4%** @1440. |
| "Escape does not close the modal" | **False** | Handler at `app.js:365`; verified `open=true` → Escape → `open=false`. |
| "0 signals on Home contradicts 3 on Signals" | **False** | Different measures, both correct: `fresh_directional: 0`, `stale_directional: 12`. See M6 for the real (copy) defect. |
| "Clock is ~3.5h wrong; IST vs UTC ambiguity" | **False** | Both formatters pin `Asia/Kolkata`; three independently sampled times agree within 5 minutes. The comparison was against a *cached* feed timestamp, not a timezone error. |

---

## 7. Recommended order

Sequenced by severity ÷ effort. Every code change listed here must land with a
guard in `tests/test_visual_consistency_audit.py` asserting **both** the
replacement and the absence of the superseded rule, and must pass
`python3 tools/mutate_design_guards.py` (mutation testing is required by
`docs/DESIGN_SYSTEM/validation.md`).

### Sprint 0 — same day, markup + one attribute
1. **C1** — drop `aria-hidden` / `tabindex` from `expandButton()` (`app.js:33`).
   Highest severity-to-effort ratio in the report.
2. **M7** — add `aria-hidden="true"` to the 10 nav glyph spans.
3. **M6** — reword the Home empty state to name the 12 stale signals.

### Sprint 1 — 1–2 days
4. **C2** — ~12-line focus trap + focus restore in the release modal.
5. **N1** — stop the nav covering `RISK CONTROL` at first paint.
6. **N2** — keep the three hero pills on one row at 390, or drop to plain text.

### Sprint 2 — 1 week, unblock style divergence
7. **C3(a)** — scope `appearance-overrides.css:209` and `:210` so Material 3 and
   Neo can opt out. 2 edits; immediately restores the type-scale difference.
8. **C3(b)** — scope or counter the style-blind `#page-tools` block.
9. **C3(c)** — reorder `dashboard.html` to foundation → styles → appearance.
   **Requires a full re-run of the 60-rendering matrix** (`docs/DESIGN_SYSTEM/validation.md` §3).

### Sprint 3 — 1 week, visual system
10. **M1** — type scale to 6 steps / 4 weights; raise the 9.5px floor.
11. **M2** — extend Neo transitions to `transform` + `box-shadow` on the four
    controls listed; respect reduced-motion.
12. **M3 / M4** — Neo padding compensation on `.tool-card` / `.metric-card` /
    `.signal-card`; Neo borders on `.chart-card` and the other seven surfaces;
    raise `.status-badge` / `.chip-option` to 2px.

### Sprint 4 — 1 week, density and structure
13. **M5** — collapse the three "no signals" sections into one compact status row
    when `fresh_directional === 0`.
14. **N5** — real routing (`pushState` + per-page URL).
15. **N3 / N4 / N6** — remove dead markup, add a footer landmark, point Neo radii
    at the tokens.

---

## Appendix — how to reproduce these numbers

```bash
# data claims
curl -s localhost:3000/api/dashboard | python3 -m json.tool | grep -A8 counts

# type scale
grep -oh "font-weight:[0-9]*" styles.css foundation.css appearance-overrides.css \
  | sort | uniq -c | sort -rn
grep -oh "font-size:[0-9.]*px" styles.css foundation.css appearance-overrides.css \
  | sed 's/font-size://' | sort -n | uniq -c

# the load-order defect (C3 cause 3)
grep -o 'rel="stylesheet" href="[^"]*"' dashboard.html

# the two style-unscoped !important rules (C3 cause 1)
sed -n '209,210p' appearance-overrides.css

# the style-blind block (C3 cause 2) — specificity (1,3,0) vs (0,2,1)
grep -n "#page-tools .tools-appearance .chip-option" appearance-overrides.css
```

Browser measurements used the real chip-click path (`applyStyle()`), never
`dataset` writes, because `initAppearance()` reverts direct writes on load.
