# Iconography — MULTIBOT2 Design System

> **Status: the current system is emoji and should be replaced in a rebuild.**
> This file documents what exists, what breaks, and what to do instead.

---

## 1. What is actually used

There is no icon library and no SVG sprite. Every glyph in the product is a raw
Unicode character typed into `dashboard.html` or emitted by `app.js`.

| Where | Glyphs | Meaning |
|---|---|---|
| Desktop nav / mobile nav | `⌂ ◆ ◷ ◉ ⚙` | Home · Signals · History · Calendar · Tools |
| Nav "M" mark | `M` + brand text | wordmark |
| Refresh buttons | `↻` | manual refresh |
| Empty states | `◇ ◈ ◷ ·` | no data |
| Signal direction | ▲ ▼ (via `direction()`) | buy / sell |
| Scan / status | `✦ ◐` | activity |
| Calendar impact | `⚠` | high impact |
| Telegram messages | `📊 🟢 ⚪ ✅` | outside the web UI |
| Appearance swatches | `<i class="appearance-swatch">` | CSS-only, correct |

## 2. Problems with emoji here

1. **They are text.** They scale with font metrics, inherit `font-weight`, and
   cannot be sized independently from their label.
2. **They render differently per platform.** `↻` on Linux is not `↻` on macOS or
   Android. A rebuild shipping these gets a different product on every device.
3. **They break `line-height`.** A glyph with emoji presentation (double-width)
   inside a 32px control shifts the control's optical centre.
4. **They are announced.** Some are read aloud as words by screen readers. A
   decorative glyph inside a labelled button is announced twice.

## 3. Accessibility rule that applies today

Every glyph that sits next to a text label is decorative and must not be announced.
The current markup gets this right by accident — the glyph is a bare text node, so
the accessible name comes from the label — but **the moment a glyph becomes its own
element** it must carry `aria-hidden="true"` or `role="presentation"`.

Accent colour swatches already do this correctly: they are empty `<i>` elements
whose names come from the visible text ("Emerald").

## 4. What a rebuild should do

**Recommendation: an inline SVG sprite, one file, no dependency.**

```
ui/icons.svg      one <svg> holding <symbol id="i-home">…</symbol> for each glyph
```

- One `<symbol>` per concept (`home`, `signals`, `history`, `calendar`, `tools`,
  `refresh`, `empty`, `buy`, `sell`, `status-ok`, `status-warn`, `impact-high`).
- Consumed with `<svg class="icon" aria-hidden="true"><use href="icons.svg#i-home"/></svg>`.
- `currentColor` for fill/stroke so icons inherit theme colour automatically —
  this is the big win: one icon set works in all 30 combinations.
- Sized by a single `.icon { width: 1em; height: 1em }` rule, never per-instance.
- `aria-hidden="true"` unconditionally. **The accessible name always comes from the
  adjacent label.** An icon-only button must carry `aria-label`.

**Do not add a third-party icon package.** It costs a network request, a build step
and a theming layer, to solve a problem an inline sprite solves in one file. The
repo has no bundler and no npm dependency; keep it that way.

## 5. Sizing rules

| Context | Size |
|---|---|
| Inside a 32px control | 16px |
| Nav item | 16–18px |
| Empty-state glyph | 17px (current `.empty-state span`) |
| Standalone brand mark | 24px |

Never exceed the line box of the label it accompanies.

## 6. Migration order

1. Ship the sprite with the new icon set; do not delete the emoji yet.
2. Swap nav icons first (highest visibility, lowest risk).
3. Swap empty states.
4. Swap direction indicators (▲/▼) — these are also colour-coded, so keep the
   shape distinction for users who cannot see the colour.
5. Remove the emoji once nothing references them.
