# Rebuild Brief — MULTIBOT2 UI

**Goal.** Rebuild the dashboard front end from scratch with a new, good-looking
interface, **preserving all 30 theme combinations** and **changing zero bot
behavior**.

**Audience.** An AI agent with no prior context in this repository.

**Read these first, in order:**

| # | Document | Why it is first |
|---|---|---|
| 1 | [`API.md`](API.md) | The seam. Everything else hangs off the HTTP contract. |
| 2 | [`LOCKED_RULES.md`](LOCKED_RULES.md) | What must not change, and what must never happen. |
| 3 | [`THEME_SYSTEM.md`](THEME_SYSTEM.md) | How 3 styles × 5 accents × 2 themes actually work. |
| 4 | [`../AI_REBUILD_SPEC.md`](../AI_REBUILD_SPEC.md) | Full bot contract, §1–30. The backend already exists — read it, don't rebuild it. |
| 5 | [`../DESIGN.md`](../DESIGN.md) | Current UI ownership + the known defects **not** to inherit. |

---

## 1. The one-sentence framing

> The bot is finished and correct. The UI is the product surface. Rebuild the
> surface; do not touch the machine underneath it.

This is a **front-end-only** rebuild. The backend is 24 Python modules, 3
strategies, 8 Supabase tables, 6 HTTP endpoints and 164 passing tests. None of it
needs rewriting. If a task requires changing a `.py` file, stop — the only
permitted server change is **adding a static-asset route** for a new UI file.

---

## 2. Why `docs/API.md` is the critical document

Before this brief, **no API contract existed**. The server is a hand-rolled
`wsgiref` app with routing inline in `main.py::web_server().app()`. The only
record of the payload shape was the minified rendering code in `app.js` —
which is simultaneously the implementation and the specification, which means
you cannot rewrite one without breaking the other.

Concretely, an agent attempting a UI rebuild would have to guess:

| Question | Unanswerable before | Answered in `API.md` |
|---|---|---|
| Is `signal` the same as `direction`? | Aliases, undocumented | §7 — both present, either readable |
| When is `pnl` available? | Unknown | §8 — `null` until closed |
| What makes a signal `actionable`? | Unknown | §7 — the exact predicate |
| Can the UI compute fresh counts? | Tempting, and wrong | §6 — server precomputes them |
| What does `null` render as? | Unknown | §12 — `—`, never `0` |
| Which endpoint can fail while healthy? | Unknown | §9 — `/api/calendar`, scrapes upstream |
| How many signals come back? | Unknown | §6 — 500, hard cap |
| Does the equity curve always have points? | Unknown | §10 — yes, at least one |

Without this document, "rebuild the UI" silently means "reverse-engineer the
UI." With it, the UI can be deleted and rewritten against a specification.

**It is now enforced.** `tests/test_api_contract.py` parses `main.py` and
`dashboard.py` and asserts the documented routes, the payload envelope, and the
computed-field contract still exist. Editing the server without updating
`API.md` fails CI.

---

## 3. Why `docs/THEME_SYSTEM.md` is the second critical document

The theme system looks like a CSS-variable swap and is not. It has an
architecture that is easy to destroy:

**Two layers that must stay separate.**
- *Style definitions* — only `styles.css` declares `--bg`, `--surface`,
  `--text`, `--accent`, `--positive` … for each style/theme/accent.
- *Shared semantic tokens* — components consume only these names.

The moment a component rule contains a hex literal or a `[data-style="neo"]`
selector, that component stops working in 10 of the 30 combinations.

**Two token *idioms* coexist.** Modern and Neo define the shared tokens as
literals. Material 3 defines a private ~50-token `--m3-*` role set and then
*binds* the shared names to it (`--surface: var(--m3-surface)`). Both idioms are
valid; what matters is that components never see the difference.

**Some rules exist only for contrast and look like mistakes:**
```css
html[data-theme="light"][data-style="neo"][data-accent="indigo"]{--accent-fill:#6163ec;--on-accent:#ffffff}
```
Scoping to `[data-theme="light"]` is load-bearing. Un-scoping it breaks dark
Neo indigo. Five token values in §4 of that document were tuned to clear AA and
will silently fail if reverted. **None of this is inferable from the CSS** — it
is exactly what documentation is for.

---

## 4. The complete document set

### Layer 0 — Identity
| Doc | Status | Purpose |
|---|---|---|
| `release_notes.APP_VERSION` | ✅ exists | Single version source |
| `tests/test_version_consistency.py` | ✅ exists | Mirrors it across 5 files |
| `tools/check_release_docs.py` | ✅ exists | Docs gate |

### Layer 1 — Locked rules
| Doc | Status |
|---|---|
| **`docs/LOCKED_RULES.md`** | ✅ **written by this brief** |
| `config.py` | ✅ executable source of truth |

### Layer 2 — Runtime architecture
| Doc | Status | Purpose |
|---|---|---|
| `AI_CONTEXT.md` | ✅ exists | Orientation, read order, repo map |
| `AI_REBUILD_SPEC.md` | ✅ exists (now complete) | §1–30, incl. full file inventory + strategy inventory |
| `multibot2-architecture.json` | ⚠️ stale pins | Regenerate after the UI changes |
| `schema.sql` | ✅ exists | Canonical DDL |
| `supabase/schema.sql` | ✅ now parity-enforced | Mirror |
| `render.yaml` | ✅ exists | Deploy + env contract |

### Layer 3 — API
| Doc | Status |
|---|---|
| **`docs/API.md`** | ✅ **written by this brief** |
| `tests/test_api_contract.py` | ✅ **written by this brief** |

### Layer 4 — Design system
| Doc | Status | Purpose |
|---|---|---|
| **`docs/THEME_SYSTEM.md`** | ✅ **written by this brief** | Tokens, 30 combos, state, shape, a11y, contrast |
| **`docs/LESSONS_LEARNED.md`** | ✅ **written by this brief** | Every defect, its root cause, and its guard |
| **`docs/START_HERE.md`** | ✅ **written by this brief** | Read order, first commands, phased build |
| `DESIGN.md` | ✅ exists | Current ownership + known defects |
| `docs/DESIGN_SYSTEM/geometry.md` | ✅ written | Spacing, radius tiers, breakpoints, nav clearance |
| `docs/DESIGN_SYSTEM/type.md` | ✅ written | Stacks, the real scale, `tabular-nums`, the <11px defect |
| `docs/DESIGN_SYSTEM/components.md` | ✅ written | Every component, state, a11y contract |
| `docs/DESIGN_SYSTEM/motion.md` | ✅ written | Durations, easings, reduced-motion, the poll rule |
| `docs/DESIGN_SYSTEM/icons.md` | ✅ written | The emoji problem and the sprite recommendation |
| `docs/DESIGN_SYSTEM/validation.md` | ✅ written | The reproducible 30×2 check |

### Layer 5 — Strategy plug-in
| Doc | Status |
|---|---|
| `STRATEGY_DEVELOPER_GUIDE.md` | ✅ exists (thin) |
| `AI_REBUILD_SPEC.md` §7–§11, §30 | ✅ now complete |
| Per-strategy conformance tests | ⚠️ only 1 of 3 |

### Layer 6 — Ops
| Doc | Status |
|---|---|
| `render.yaml` | ✅ |
| `LOCKED_RULES.md` §9 | ✅ |

### Layer 7 — Tests & CI
| Doc | Status |
|---|---|
| `.github/workflows/tests.yml` | ✅ Python 3.12, `pip install -e ".[test]"`, compileall, import discovery, pytest |
| 164 tests / 34 files | ✅ |

### Layer 8 — Repository hygiene
| Item | Status |
|---|---|
| `.gitignore` covers vendored tooling | ✅ now |
| 71 agent-skill files still tracked | ⚠️ needs a deliberate `git rm --cached` |
| `AUDIT_DESIGN_CONSISTENCY.md`, `DASHBOARD_AUDIT_FRESH.txt` | ⚠️ stale; `DASHBOARD_AUDIT_FRESH.txt` claims `WHATS_NEW.md` is v3.2.8 (now 3.3.0) |

### Layer 9 — Process
| Doc | Status |
|---|---|
| `docs/DECISIONS/` (ADRs) | ❌ **missing** — every "why" currently lives in a known-defects list |
| `docs/ONBOARDING.md` | ❌ **missing** |

---

## 5. What must NOT be inherited

| # | Anti-pattern | Why | Instead |
|---|---|---|---|
| 1 | **3-sheet override cascade** (`styles.css` → `foundation.css` → `appearance-overrides.css`) | `DESIGN.md` itself records that rules past ~50 KB are unreachable and must be "corrected from the appearance layer." That trap *created* 84 KB of patch-on-patch in `appearance-overrides.css`. | Ordered layers: `tokens → base → components → themes`, zero overrides |
| 2 | **`app.js` at 49 KB** — rendering, state and event wiring mixed | Cannot be edited safely | Split by page: `overview.js`, `signals.js`, `history.js`, `calendar.js`, `tools.js` |
| 3 | **Two divergent `schema.sql`** | Caused silent loss of scan history | One canonical file + a parity test |
| 4 | **`main.py` bare globals** | `LOCK = RLock()` declared at line 25, but `NEWS_PAUSE_ENABLED` and `LAST_PING_AT` mutate unguarded | One `RuntimeState` object, always under the lock |
| 5 | **No API contract** | Made a UI rebuild guesswork | `docs/API.md` + `tests/test_api_contract.py` |
| 6 | **Hardcoded invariants in the UI** | Money, risk, asset count drift | Read them from `/api/dashboard` (`system`, `rules`, `universe`) |
| 7 | **`/architecture` reads from a vendored third-party dir** | `agent/skills/archify/…html` — a UI route depending on vendored tooling is fragile | Move to a tracked first-party path |

---

## 6. Execution plan

### Phase 0 — Freeze (do not skip)
- [ ] Read `API.md`, `LOCKED_RULES.md`, `THEME_SYSTEM.md` in full.
- [ ] Run the suite: `python3 -m pytest` → must be **164 passed**.
- [ ] Start the app and record a baseline screenshot set for **all 30
      combinations × 2 viewports**. This is the visual regression target.
- [ ] Capture the live `/api/dashboard` response and save it as a fixture.
      Golden-file testing is how you prove behavior did not change.

### Phase 1 — Foundations (no visual change)
- [ ] Write `ui/tokens.css` — every token from `THEME_SYSTEM.md` §2, values
      from §3. **No component rules, no literals outside token definitions.**
- [ ] Write the 30 theme blocks from §3–§4, including both `[data-theme="light"]`-scoped
      Neo fixes and the five tuned contrast values.
- [ ] Port `appearance.js` unchanged, minus the legacy-listener suppression
      shim (there will be no legacy listener).
- [ ] **Verify:** contrast test passes on all 30 × 2; `data-style`/`data-theme`/
      `data-accent` still toggle correctly.

### Phase 2 — Shell and primitives
- [ ] `ui/base.css`: reset, type scale, spacing, app shell, bottom nav.
- [ ] Port the **ExpandableControl contract** verbatim (`THEME_SYSTEM.md` §6).
- [ ] Component primitives: buttons, chips, cards, metric tiles, badges,
      tables, empty states, modal.
- [ ] **Verify:** 44 controls all ≥ 32×32; no horizontal overflow at either
      viewport; exactly one `<h1>` visible.

### Phase 3 — Pages, one at a time
Order matters — each is independently shippable.
- [ ] `#page-overview` → `#page-signals` → `#page-history` →
      `#page-calendar` → `#page-tools`.
- [ ] Wire to `/api/dashboard` only. `/api/calendar` and `/api/backtest` are
      user-triggered and come with `#page-calendar` / `#page-tools`.
- [ ] **Verify per page:** payload fixture renders identically to the old UI;
      no client-side recomputation of freshness/counts/actionability.

### Phase 4 — Accessibility (not optional, not last)
- [ ] **Close the card-row defect.** `.card-body`/`.card-main` is a
      `<div data-expand>` with no `role` and no `tabindex`. 8 bodies, **0
      focusable** — a WCAG 2.1.1 failure today. Make it focusable with a key
      handler, or remove the div handler and rely on the real `.expand-button`.
- [ ] **Close the live-region defect.** 11 polled values update silently. Wrap
      a consolidated status summary in `aria-live="polite"` rather than adding
      11 regions, which would make a screen reader unusable.
- [ ] Add a skip link; `<main>` currently has no `id`.
- [ ] `tabular-nums` on `.workspace-count` and `.inline-status`, which still
      read `normal` while the metric cards are fixed.
- [ ] **Verify:** keyboard-only pass over every page; `axe` clean on all 30.

### Phase 5 — Cutover
- [ ] Delete the old CSS and `app.js` only after Phase 4 passes.
- [ ] Add new assets to the `files` dict in `main.py::web_server()` — **there is
      no directory listing**; an unregistered file 404s.
- [ ] Update `DESIGN.md` ownership table, `multibot2-architecture.json`,
      `tests/test_dashboard_ui.py`.
- [ ] Re-run the full suite plus the contrast matrix.

---

## 7. Acceptance criteria

A rebuild is done when **all** of these hold:

| # | Criterion | How to check |
|---|---|---|
| 1 | Zero backend behavior change | `/api/dashboard` response is byte-identical to the Phase 0 fixture, modulo timestamps |
| 2 | All 30 combinations render | Screenshot every combination × 2 viewports |
| 3 | 0 WCAG AA contrast failures | `tests/test_contrast_tokens.py` extended to `--surface-2`/`--surface-3` |
| 4 | No horizontal overflow | 1440×900 and 390×844 |
| 5 | Every interactive target ≥ 24px | Enumerated in the DOM |
| 6 | Full keyboard operability | Includes the previously mouse-only card rows |
| 7 | Polled updates announced | Live regions verified with a screen reader |
| 8 | Exactly one `<h1>` visible | Per page |
| 9 | `docs/API.md` still accurate | `tests/test_api_contract.py` green |
| 10 | Suite still fully green | `python3 -m pytest` |
| 11 | No `transition: all` | grep |
| 12 | Reduced-motion honoured | All sheets |
| 13 | Version flows from the server | UI renders the received `version`, never a build-time literal |

---

## 8. The rule that prevents most failure

**Nothing recomputes server truth in the browser.**

The server already computes `freshness`, `age_minutes`, `has_trade_levels`,
`actionable`, every `count`, and `signal_summary`. Money formatting and
timestamp rendering *are* the UI's job; deciding whether a signal is tradeable
is not.

Recomputing these client-side is the single most likely way a UI rebuild
silently changes bot behavior — the dashboard would agree with itself and
disagree with the Telegram message the user already received.

---

## 9. Where the real risks are

| Risk | Severity | Mitigation |
|---|---|---|
| Recomputing server truth client-side | High | §8. Read `actionable`; never derive it |
| A component rule hardcodes a colour | High | Phase 1 tokens-only; grep for hex in `components.css` |
| Dropping a theme combination during the port | High | Screenshot all 30; the contrast test enumerates them |
| Un-scoping the Neo light-only accent fixes | Medium | Called out explicitly in `THEME_SYSTEM.md` §4 |
| Silently regressing contrast | Medium | Extend the wash test to `--surface-2` and `--surface-3` |
| Not registering new assets in `main.py` | Medium | There is no static directory listing |
| Treating `/api/calendar` as reliable | Medium | It scrapes an external site; render a real error state |
| Carrying over the override cascade | Medium | §5 — the whole point of the rewrite |

---

## 10. Status

**Written by this brief:** `docs/REBUILD_BRIEF.md`, `docs/API.md`,
`docs/LOCKED_RULES.md`, `docs/THEME_SYSTEM.md`, `tests/test_api_contract.py`.

**Completed in the follow-up pass:** all six `docs/DESIGN_SYSTEM/*` files,
`docs/LESSONS_LEARNED.md` (every defect with its guard), `docs/START_HERE.md`
(entry point and build order), and `tests/test_frontend_syntax.py`.

**Still open for a future pass:** the per-strategy conformance suites for
`adaptive_trend` and `sweep_v2`, ADRs under `docs/DECISIONS/`, focus restoration
for the date-group / history / calendar toggles (see `LESSONS_LEARNED.md` C3), and
the stale untracked audit artefacts in §4 Layer 8.
