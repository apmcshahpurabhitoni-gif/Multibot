# Validation — MULTIBOT2 Design System

The reproducible check that a UI change is safe. Run **all of it** before shipping a
visual change.

---

## 1. The matrix

| Axis | Values | Count |
|---|---|---|
| Style | `modern`, `material3`, `neo` | 3 |
| Accent | `emerald`, `indigo`, `amber`, `rose`, `cyan` | 5 |
| Theme | `light`, `dark` | 2 |
| Viewport | `1440×900`, `390×844` | 2 |

**30 combinations × 2 viewports = 60 renderings.** Every one must pass.

## 2. Automated (no browser) — in CI

```bash
python3 -m pytest
```

Covers, without a browser:

| Check | Test |
|---|---|
| WCAG AA contrast, all 30 combos, wash-over-`--surface` **and** `--surface-2` | `test_contrast_tokens.py` |
| Theme/style/accent axis still 3 × 5 × 2 | `test_api_contract.py` |
| Only `styles.css` declares contrast tokens | `test_api_contract.py` |
| JavaScript parses (`node --check`) | `test_frontend_syntax.py` |
| Stylesheet load order unchanged | `test_frontend_syntax.py` |
| `async` keyword intact on functions using `await` | `test_frontend_syntax.py` |
| Geometry, radius tiers, control sizes, reduced-motion, no `transition: all` | `test_dashboard_ui.py` |

> **Mutation-test any new guard.** Revert the fix it protects and confirm the test
> fails. A test that passes on the broken state is worse than no test.

## 3. Browser sweep (required before merge)

Switching themes must be done through **`localStorage` + reload**, not by setting
the attribute:

```js
localStorage.setItem('mavis-style','neo');
localStorage.setItem('mavis-accent','amber');
localStorage.setItem('mavis-theme','light');
location.reload();
```

> **Why this matters.** `app.js::initAppearance()` reads `localStorage` and
> overwrites `dataset.style` on every bootstrap. Setting the attribute directly is
> silently reverted — a sweep done that way measures `modern` thirty times and
> reports a confident, wrong result. This cost real debugging time once already.

Then, for each of the 60 renderings, assert:

| # | Assertion | Method |
|---|---|---|
| 1 | No horizontal overflow | `document.documentElement.scrollWidth <= innerWidth` |
| 2 | No interactive target < 24px | walk every `button, a, [role=button], input, select` |
| 3 | Exactly one visible `<h1>` | count `h1` with `offsetParent !== null` |
| 4 | No unnamed interactive element | every control has text or `aria-label` |
| 5 | No unlabelled input | every input has `aria-label` or a `<label>` |
| 6 | Body copy ≥ 4.5:1 | see contrast test |
| 7 | Only the chevron rotates | no container-level `transform` on `.collapse-control` |
| 8 | Card rows are keyboard reachable | `tabIndex >= 0` on `.card-main[data-expand]` |
| 9 | Live region updates | `#dashboardAnnouncer` text changes after a poll |
| 10 | Skip link works | first Tab reaches it; it targets `#main-content` |

## 4. Command reference

```bash
playwright-cli open "http://127.0.0.1:3000/dashboard" --idle-timeout 0
playwright-cli sleep 20          # the /api/dashboard payload is ~600KB; wait for it
playwright-cli resize 1440 900
playwright-cli eval "<js>" --filename out.json
```

Gotchas learned the hard way:

- **Set + measure in ONE `eval`.** Across separate invocations the 30s poll
  re-renders and resets the appearance.
- **The browser caches `styles.css`.** Re-issue `open` after a CSS edit or you will
  measure the old sheet.
- **Settle ≥ 500ms** after switching a combination, or you get phantom failures.
- Hidden pages are `display:none`, so `querySelectorAll` finds rows that
  `focus()` will not reach. Check `offsetParent` before testing focus.

## 5. Definition of done

A UI change is complete when:

- [ ] `python3 -m pytest` fully green
- [ ] 60/60 renderings visually reviewed (screenshot grid)
- [ ] Overflow, target size, heading count, naming all pass in-browser
- [ ] Keyboard-only walkthrough of every page
- [ ] Screen-reader spot check on the poll announcement
- [ ] Reduced-motion confirmed
- [ ] `/api/dashboard` response unchanged (compare a golden fixture)
