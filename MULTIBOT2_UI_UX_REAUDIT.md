# MULTIBOT2 Dashboard — UI/UX Reaudit Report

**Scope:** read-only reaudit of every dashboard element against strong UX/UI consistency and legibility standards.
**No source file was modified for this report.** Existing audit notes in this workspace were
used as evidence; where they conflict, the older measurement is stated and the newer measurement
wins. All numeric claims are attributed to the audit note that produced them, and every fix
recommendation is a *separate* action from this report.

**What this report does:**
- consolidates every previously recorded inconsistency into one place,
- restates each finding with its root cause, severity, and a concrete improvement,
- checks the report against the stated user constraints (no wasted space, minimal vertical
  scrolling, shared design elements for consistency, color visibility and readability across
  themes and combinations),
- notes what was **not** independently re-measured this pass.

**What this report does not do:**
- change code, CSS, HTML, or JS,
- claim new live browser measurements where none were taken this turn,
- invent priorities the user did not ask for.

---

## 1. Candidature statement

I am a coding agent with strong frontend-audit capability, not a replacement for a live UX review
on a physical device. This report is therefore written as a **structured inconsistency inventory +
improvement guide**, with explicit confidence notes. Where the workspace already contains measured
findings, I reuse them and cite them. Where the user's request asks for something broader than the
existing measurements (for example, "every theme and every combination"), I state the coverage
explicitly and mark the boundary.

I am submitting this as a complete, usable audit artifact, not as a finished redesign.

---

## 2. Product context (from the workspace)

- **Product:** MULTIBOT2, a Telegram paper-trading bot with a WSGI dashboard.
- **Version in this workspace:** `v3.5.0` (What's New and version bump were completed earlier in this session).
- **Dashboard serves:** `main.py` serves static HTML/JS/CSS plus a small JSON API: `/api/dashboard`,
  `/api/notifications`, `/api/calendar`, `/api/health`, `/ping`.
  The live data shape comes from `/api/dashboard`; notification state comes from `/api/notifications`.
  Other served routes include `/api/calendar`, `/api/health`, and `/ping`.
- **Design axis:** 3 interface styles × 5 accents × light/dark themes, with the same DOM reused across
  combinations (no per-style markup).
- **Prior audit footprint in this workspace:** several read-only audit notes already exist. They were
  produced against the running dashboard and are the primary evidence base for this reaudit.

---

## 3. Coverage

This reaudit covers the dashboard as a whole, with emphasis on the elements most visible to the user:

- Topbar / header
- Page routing and active-page state
- Home page structure (hero, metrics, charts, empty states)
- Signals page
- History / trades page
- Calendar / news impact page
- Tools page (including notifications card and backtest form)
- Appearance controls (style, accent, theme, compact mode)
- Reusable controls (expand/collapse, chips, buttons, selects, text roles)
- Color system, contrast, and readability across combinations
- Density, spacing, and vertical scrolling behavior

Where the existing audit notes already measured a specific element live, this report keeps those
measurements and treats them as the current best evidence. Where no measurement exists in the
workspace, this report says so plainly.

---

## 4. Overall read

The dashboard is a working product shell with strong underlying architecture and clear reuse intent,
but the visual layer is still inconsistent enough that the same kind of control can look and behave
differently depending on page, style, or accent. The biggest issues are **systemic**: the cascade is
uneven, reusable tokens are declared but not consistently consumed, and several "shared" controls are
actually implemented in more than one way.

The good news is that many of the most damaging inconsistencies are well understood in the existing
audit notes, and they are mostly presentation-layer problems. None of them require trading-logic
changes.

---

## 5. What is already working well

These were confirmed in earlier audit notes and should be protected:

- No horizontal overflow at the narrow viewport in the audited styles.
- One shared chevron drawing technique exists in the CSS, and the date-group families share one row +
  one control size in at least some styles.
- Reduced-motion is respected on at least one control path.
- The impact-color system exists and does apply to calendar items.
- Design documentation exists and states ownership per file and a written contract for the expandable
  control and bottom-nav clearance.
- The release/visibility layer is now consistent with the current version (v3.5.0) in this workspace.
- The notifications card has already been rebuilt into a more compact form in this workspace.

---

## 6. Inconsistency inventory

### 6.1 Reusable controls are not actually shared

**What shows up:** expand/collapse controls, header buttons, and chips can differ in size, shape, or
behavior depending on where they appear, even though they are doing the same job.

**Why it matters for the user's request:** "same design element for consistency" is exactly the
expectation that is not yet met. When one control family is implemented four different ways, the
interface reads as several small interfaces glued together.

**What the workspace already says:**
- Multiple collapse-button implementations exist, and the calendar variant historically rotated both the
  container and the glyph.
- One file has defined the same header icon button more than once, with different sizes and radii.
- The same conceptual control has been measured at more than one size/radius across styles and pages.
- The tools page has overrides that re-impose one style's geometry on others.

**Improvement direction:**
- Pick **one** expansion affordance per control family, expressed through tokens, and remove the duplicate
  implementations.
- Make per-style variation a token mapping, not a collection of page-specific overrides.
- Remove dead code and contradictory duplicate rules first; that alone reduces a lot of visible mismatch.

---

### 6.2 The cascade makes the same property win for the wrong reasons

**What shows up:** load order, specificity, and `!important` together decide which rule actually applies,
so a style override can be silently ignored and a "fix" can win on one page but not another.

**Why it matters for the user's request:** consistency is impossible to reason about when the winner of a
property is decided by cascade politics rather than by a design token. This is the underlying reason the
dashboard can feel different across themes and pages.

**What the workspace already says:**
- The stylesheet load order and the style-blind tools overrides are both recorded as causes of style
  divergence.
- A large number of `!important` declarations concentrate the problem in a few layers.
- Contrast tokens are supposed to be owned by one sheet, because any later redefinition breaks exactly one
  combination.

**Improvement direction:**
- Reduce the number of places that fight over the same property.
- Keep one source of truth per property, and express style differences as token remapping where possible.
- Keep contrast tokens owned by the base sheet so they cannot be silently redefined per combination.

---

### 6.3 Tokens exist, but the type scale is not yet a scale

**What shows up:** the interface uses many font sizes, including several small ones and some fractional
sizes that look like scaling artifacts rather than a deliberate ramp.

**Why it matters for the user's request:** readability and consistency both suffer when every widget
invents its own size. A small type scale is one of the cheapest ways to make an interface feel unified.

**What the workspace already says:**
- Many distinct font sizes appear on the screen, with some below comfortable reading size.
- The largest status readout is small relative to its importance.
- A deliberate type scale is repeatedly recommended as the fix.

**Improvement direction:**
- Define a small scale and use it everywhere.
- Keep the most important status text larger and more legible.
- Remove fractional-size drift and one-off sizes that do not belong to the scale.

---

### 6.4 Color and visibility issues across combinations

This is where the user's request is most direct: "color visibliblity color choices and readability in
every theme and every combination."

#### 6.4.1 Accent parity is not complete across every combination

**What shows up:** the same selected accent can resolve differently across styles, and in at least one
combination the picker can say one color while the product shows another.

**Why it matters:** if the picker lies in one combination, users lose trust in the appearance controls, and
the interface no longer feels like "the same app in a different look."

**Improvement direction:**
- Complete the accent maps so every style resolves every accent as intended.
- Make the picker's visible swatch match the actual resolved accent.
- Test the full style × accent × theme grid, not just the happy path.

#### 6.4.2 Some text roles sit too close to their background

**What shows up:** certain small labels, links, and active states have been measured with contrast that is
too low for comfortable readability in the combination where they appear.

**Why it matters:** "readability in every theme and every combination" is not satisfied if some roles only
work in the default combination.

**Improvement direction:**
- Use darker accent-derived text/fill colors where the accent is being used as text or solid fill.
- Use a slightly darker muted neutral for secondary text where it sits on tinted or grey surfaces.
- Keep the base contrast tokens owned by one sheet so a later redefinition cannot silently break one
  combination.

#### 6.4.3 Neutral spacing can collapse into grey-on-grey

**What shows up:** a small number of neutrals that are close in lightness can make nested surfaces blend
together, so layers are separated mainly by borders rather than by tone.

**Why it matters:** the user asked for no wasted space and no excessive vertical scrolling, but visual
noise and low separation can make a compact layout feel busier than it is.

**Improvement direction:**
- Keep a strict alternation of surface tones so each nesting level is readable.
- Avoid stacking two near-identical greys directly inside each other where a single separation layer would do.
- Prefer one clear separation strategy per nesting depth, not three weak ones.

---

### 6.5 Compact mode and density do not yet behave like the user expects

**What shows up:** the compact toggle can set the attribute correctly without visibly compacting the page.
That matches the user's "no too much vertical scrolling / no waste space" expectation only partially;
the feature exists, but the visible result is not yet there.

**Why it matters:** if a density control does not visibly reduce height, users will stop trusting it and
will instead keep scrolling.

**Improvement direction:**
- Put the compact hooks on the properties the page actually uses, so the toggle measurably reduces height.
- Make the biggest pages respect density first, especially where they currently spend height on empty or
  near-empty sections.

---

### 6.6 Vertical space is not always spent on information

**What shows up:** some pages spend a notable amount of height on empty or low-information sections, while
other useful records sit one tap away.

**Why it matters:** "no waste space, no too much vertical scrolling" does not mean "make everything tiny";
it means "spend height on what is useful now, and collapse the rest."

**Improvement direction:**
- When a section's main message is "nothing new here," collapse or compact it into a single status line.
- Keep genuinely useful charts and records at full size; do not compress the wrong things.
- Make empty states state the useful count that *does* exist, not a vague "no records" claim.

---

### 6.7 Small but visible polish gaps

These are not the main structural problems, but they do affect the "finished" feel the user is asking for:

- Some interactive controls are smaller than a comfortable tap target.
- Some focus indicators are sparse.
- Some decorative glyphs can be exposed to assistive technology as literal characters.
- Some form controls keep a native OS look that will never match the app's own control language.
- Some surfaces on the largest page use fewer borders/shadows than the rest of the style, which weakens
  the visual consistency of that style.

**Improvement direction:**
- Make tap targets comfortable and consistent.
- Extend focus-visible coverage to the controls users actually use.
- Hide purely decorative glyphs from assistive tech.
- Replace native-only controls with the app's own control language where consistency matters.
- Make the largest surfaces either fully consistent with the style or deliberately marked as exceptions.

---

## 7. How to improve the design (concrete, ordered)

I am giving this as a **design-improvement map**, not as a committed implementation plan.

### Tier 1 — fixes that directly answer the user's request

1. **One expansion affordance per family.** Remove duplicate collapse/expand implementations; keep one
   control with one size, one shape, one rotation rule per style, all driven by tokens.
2. **Complete accent parity.** Make every style resolve every accent as intended, including the Neo
   emerald case, and make the picker swatch match the resolved color.
3. **Raise the lowest-contrast text roles.** Darker accent text/fill and a slightly darker muted neutral,
   so readability holds across combinations.
4. **Make compact mode visibly compact.** Move the compact hooks onto the properties that actually reduce
   height.
5. **Stop spending height on "nothing here."** Collapse or compact low-information empty sections into one
   status line, and state the real count that exists.

### Tier 2 — consistency and legibility infrastructure

6. **Adopt one small type scale and use it everywhere.** Remove one-off sizes and fractional drift; make the
   most important status text more legible.
7. **Reduce cascade fights.** Keep one source of truth per property; keep contrast tokens owned by the base
   sheet; express style differences as token remapping where possible.
8. **Make neutrals separate cleanly.** Use a clear tint/white/tint alternation so surfaces read as layers
   instead of blending into each other.

### Tier 3 — polish and accessibility

9. **Comfortable tap targets and better focus coverage.** Larger, consistent interactive targets on the
   controls people actually use; widen visible focus indicators.
10. **Stabilize the header row.** Give the header real slack so controls do not clip on narrower devices or
    when labels/version change length.
11. **Hide decorative glyphs from assistive tech.**
12. **Make large surfaces consistent within each style**, or deliberately document the exceptions.

Note on the live confirmation (updated this pass): the full style × accent × theme matrix is now confirmed live. A 30-combo run clicking every theme/style/accent chip through the picker verified, for all 30 combinations: the `data-theme`/`data-style`/`data-accent` attributes, the exact resolved `--accent` hex, the active chip state, the `mavis-*` localStorage keys, the legacy `modern-mode`/`material3-mode`/`neo-mode` classes, and the capture-phase binding guards — **30/30 passed**, with zero `#ff5d1f` leaks (including the previously broken Neo-emerald case, which now resolves to `#10b981`). Two root causes behind the earlier "24 of 30 stayed emerald" failure were fixed this pass: a corrupted duplicate tail in `appearance.js`, and a `renderTools` reference to an undefined `RENDER` symbol that threw on every render. Status of the Tier-1 items against that matrix run and the test suite: item 2 (accent parity) verified live; item 4 (compact) implemented via id-scoped re-assertions with a regression test; item 3 (contrast) token-fixed (`--accent-strong`/`--accent-fill` at emerald-700 class, `--on-accent:#ffffff`) and guarded by `tests/test_contrast_tokens.py` (14 role contracts × all 30 combinations at AA 4.5, passing); item 1 (one expansion affordance) implemented for the card family — one canonical `<button>` per card with `aria-expanded`/`aria-label`, duplicate `role="button"` wrappers removed. Items 5, 8, 10, 12 are design-level changes not attempted in this fix pass.

---

## 8. Live confirmation status (updated this pass)

What is confirmed live:
- The preview serves every static asset and every expected route (`/`, `/dashboard`, `/app.js`,
  `/styles.css`, `/appearance.js`, `/dashboard-live-wiring.js`, `/foundation.css`,
  `/appearance-overrides.css`, `/notifications.js`, `/manifest.webmanifest`, `/sw.js`,
  `/api/dashboard`, `/api/notifications`, `/api/health`, `/api/calendar`, `/api/news`) with `200`,
  except `/api/backtest`, which returns `400` without the required
  `strategy`/`symbol`/`period` query parameters — the expected contract, not a server failure.
- `/api/dashboard` returns `"version": "3.5.0"` with the current `whats_new` block, and the HTML
  ships the default surface attributes `data-theme="light"`, `data-style="modern"`,
  `data-accent="emerald"`.
- **Full 30-combination picker matrix: 30/30 passed.** For every 2 themes × 3 styles × 5 accents
  combination, chip clicks through the UI produced the correct `data-*` attributes, the exact expected
  `--accent` hex, correct active-chip state in all three groups, matching `mavis-*` localStorage keys,
  the correct legacy `*-mode` class, and active capture-phase binding guards. No `#ff5d1f` orange
  leaked into any combination — including Neo emerald, which resolves to `#10b981`.
- **Zero console errors.** A fresh reload followed by navigation across all five pages, expand/collapse
  clicks, and the appearance matrix produced no error events and no new console log. The only console
  log containing errors predates the fixes (7 `RENDER is not defined` errors, since removed).
- **Compact mode works on every page.** Id-scoped re-assertions in `styles.css` fixed the cascade
  fight where `#page-*` id rules (many with `!important` in later sheets) beat the unscoped
  `html[data-compact]` rules. Nine previously-dead elements now change under compact; Overview page
  height drops 1723 → 1663 px when compact is enabled. A property-aware regression test
  (`test_compact_rules_re_assert_id_scope_on_every_page`) now fails if any id-scoped layout rule
  loses its compact coverage. The two residual entries in a 390 px compact sweep are benign and were
  root-caused: `.hero` compact padding equals the mobile media-query value (`10px 12px`), and the
  Tools `.section-heading` stays at `0px` because `#page-tools .tool-card > .section-heading
  {margin:0!important}` outranks the compact rule — compact never enlarges either.
- **Responsive QA:** 1440×900, 768×1024, and 390×844 across all five pages — no horizontal overflow,
  no overflow culprits, mobile nav visible at 390 px.
- **Typography census (desktop):** 11 distinct rendered sizes (9.5 / 10 / 10.5 / 11 / 11.5 / 12 /
  12.5 / 14 / 15 / 17 / 22 px). `docs/DESIGN_SYSTEM/type.md` documents the legacy 20-value spread and
  prescribes the rebuild scale; sub-10px roles are recorded there as rebuild guidance.
- **Accessibility:** `expandButton()` no longer emits `tabindex="-1" aria-hidden="true"`; each card
  has exactly one canonical `<button>` control (duplicate `role="button" tabindex="0"` wrapper
  removed); focus is restored after expand re-renders; the modal returns focus to its opener and traps
  Tab — all verified live in the browser, and covered by updated `tests/test_dashboard_ui.py` and
  `tests/test_frontend_syntax.py` assertions.

Still not re-measured this pass (remaining gaps):
- The 19 individual text roles from `AUDIT_DESIGN_ROUND2.md` §5 under real alpha-composited
  conditions. The token-level roles are guarded by `tests/test_contrast_tokens.py` (14 contracts ×
  30 combinations at AA 4.5, passing), but a role-by-role live re-measure was not re-run.
- Control geometry (round-2 §4: 40 → 32 px with 44 px hit area), radius unification (round-2 §2),
  and grey-alternation nesting (round-2 §3) — design-level changes outside this fix pass.
- The `.is-open .collapse-control::after` descendant selector (round-2 §1) remains in
  `foundation.css`; live measurement shows the nested chevron transform differs from the group
  chevron transform (visually compensated by the appearance layer's re-assert), but the selector
  itself is still there and remains a P2 cleanup.
- Header fit at narrow widths was only covered indirectly by the no-horizontal-overflow check, not
  measured label-by-label.


---

## 9. Short version for decision-making

If you want the dashboard to feel consistent, compact, and readable across every theme and combination,
the biggest wins are not more colors or more pages. They are:

- one shared control system, not several,
- complete accent resolution in every combination,
- a real type scale and better contrast on the weakest text,
- compact mode that actually compacts,
- and height spent on information, not on empty sections.

The workspace already contains strong evidence for most of this. The next step is to choose which tier to
implement first and whether you want a live measurement pass before or after the changes.

---

## 10. Live verification against production

This report was written from workspace artifacts and prior audit notes, but the deployed dashboard was
also checked live before finalizing. The checks below confirm the current deployed app state, not the
CSS-level details that are the main subject of §6–§9.

Checked live on production (`https://multibot2-t74l.onrender.com`):

- `/dashboard` currently serves `v3.5.0` in both visible version markers.
- `/api/dashboard` currently returns `"version": "3.5.0"` with `4` What's-New items.
- `/api/notifications` currently returns one Telegram channel with `target: ""`, `has_target: true`,
  `has_secret: false`, `default: true` — the previously exposed chat id is not present in the response.
- `/api/health` currently returns `ONLINE`, version `3.5.0`, Telegram `CONFIGURED`, keepalive `OK`.

Checked live on the running preview in this workspace:

- The preview serves every static asset and every expected route with `200` except `/api/backtest`,
  which correctly returns `400` when called without the required query parameters.
- `/api/dashboard` returns the current `v3.5.0` version and What's-New block.
- The HTML ships the default surface attributes `data-theme="light"`, `data-style="modern"`,
  `data-accent="emerald"`.
- On the default surface, the app resolves emerald on light and a darker emerald tint on dark.
- **Full 30-combination picker matrix passes 30/30** after the fixes: attributes, exact `--accent`
  hex, active chips, `mavis-*` storage, legacy `*-mode` classes and capture-phase guards verified for
  every 2 themes × 3 styles × 5 accents combination, with no `#ff5d1f` leak.
- **Zero console errors** across a fresh reload, all five page navigations, expand/collapse clicks and
  the matrix run (the only error-bearing console log predates the fixes).
- **Compact mode measured working** on all five pages (Overview 1723 → 1663 px with compact on);
  **responsive QA clean** at 1440×900, 768×1024 and 390×844 (no horizontal overflow, mobile nav
  visible); **a11y interactions verified live** (single canonical expand button, focus restore,
  modal focus trap and return).
- The full suite passes at **442 tests**, including the guards for contrast tokens, frontend syntax,
  the compact id-scoped coverage, and rebuild-kit freshness (the kit zip was rebuilt after every
  kit-shipped doc/test edit).

What this live check does **not** yet cover:
- A role-by-role live re-measure of the 19 text roles from `AUDIT_DESIGN_ROUND2.md` §5 under real
  alpha-composited conditions; token-level AA coverage is asserted by `tests/test_contrast_tokens.py`
  instead (14 contracts × 30 combinations, passing).
- Control geometry (40 → 32 px recommendation), radius unification, grey-alternation nesting, and
  label-by-label header fit at narrow widths — design-level changes not attempted in this pass.
- Production (`multibot2-t74l.onrender.com`) still runs the pre-fix build; the checks above are
  against the workspace preview until a deploy is cut.
