# Motion — MULTIBOT2 Design System

Extracted from the shipped stylesheets at v3.3.0.

---

## 1. The three rules

1. **Never `transition: all`.** Every transition names its properties explicitly.
   Verified: zero occurrences across all three sheets.
2. **Reduced motion is honoured** in all three sheets via
   `@media (prefers-reduced-motion: reduce)`, which sets `transition: none !important`.
3. **Only the chevron rotates.** Container transforms are forbidden — see
   [`../THEME_SYSTEM.md`](../THEME_SYSTEM.md) §6, the ExpandableControl contract.

## 2. Durations in use

| Duration | Properties | Typical use |
|---|---|---|
| `.15s ease` | `background`, `color`, `border-color`, `transform` | hover and press states |
| `.16s ease` | `background`, `color`, `border-color`, `box-shadow`, `transform` | slightly heavier hover |
| `.18s ease` | `box-shadow`, `transform`, `border-color` | elevation change on hover |
| `.2s ease` | `background`, `color`, `opacity` | fades, drawer |
| `.25s ease` | `background`, `color` | rare, deliberate |

**Only `.15s`–`.25s`.** Nothing in the product animates longer. A rebuild that
introduces a 400ms+ transition on a frequently-repeated control will feel wrong
next to a 30-second data poll.

## 3. Easing

`ease` everywhere. There are **no** cubic-bezier curves, springs, or keyframes in
the current system. Adding one is a style decision, not a bug fix — keep it
deliberate and put it in `appearance-overrides.css` (or `themes.css` in a rebuild),
never scattered through component rules.

## 4. What may animate

| Allowed | Forbidden |
|---|---|
| `background-color` | `width` / `height` / `top` / `left` (layout shift) |
| `color` | `transform` on a container that holds a chevron |
| `border-color` | anything on `:root` / `<html>` |
| `opacity` | |
| `transform` on icons only | |
| `box-shadow` | |

`.skip-link` is the one deliberate `top` transition (`top .15s ease`) — it is a
keyboard-only control that must appear instantly on focus, so a short slide is
preferred over a hard cut.

## 5. The 30-second poll

The dashboard re-fetches and re-renders **every 30 seconds**
(`CONFIG.refreshMs = 30000`). Two consequences:

- **Never animate a value that changes on the poll.** Money, counts and status
  must snap. If they animate, every 30 seconds the whole screen twitches.
- Because re-render replaces DOM nodes via `innerHTML`, **focus is destroyed**.
  Anything keyboard-interactive inside a re-rendered list must restore focus
  afterwards. The card rows now do this; the date-group toggles and history rows
  do not, and should.

## 6. Verification

- `grep -rn "transition:\s*all" *.css` → must return nothing.
- Every stylesheet must contain a `prefers-reduced-motion` block.
- Toggle the OS reduced-motion setting and confirm nothing moves.
