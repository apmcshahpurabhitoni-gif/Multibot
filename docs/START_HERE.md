# START HERE — Building the New MULTIBOT2 UI

You have the contracts. This is the order to use them in.

---

## 1. What you are building

**A new dashboard front end. Nothing else.**

The bot is finished: 24 Python modules, 3 strategies, 8 Supabase tables, 6 HTTP
endpoints, 192 passing tests. **Do not rewrite it.** If a task requires changing a
`.py` file, stop — the only permitted server change is **adding a static-asset
route** for a new UI file.

Success looks like: the same bot, a visibly better interface, **all 30 theme
combinations** still working, and `/api/dashboard` returning a byte-identical
payload.

---

## 2. Read in this order

| # | File | Read it for |
|---|---|---|
| 1 | **`API.md`** | Every endpoint, every payload field, the `actionable` predicate, the `—` convention. **You cannot start without this.** |
| 2 | **`LOCKED_RULES.md`** | The 11 invariants you may not change, and the 10 things a rebuild must never do. |
| 3 | **`THEME_SYSTEM.md`** | How 30 combinations work; why a component rule may never contain a hex literal. |
| 4 | **`LESSONS_LEARNED.md`** | The defects that already shipped here. **Do not rediscover them.** |
| 5 | **`REBUILD_BRIEF.md`** | The 6-phase plan, acceptance criteria, risk table. |
| 6 | `DESIGN_SYSTEM/*.md` | Geometry, type, components, motion, icons, validation. |
| 7 | `AI_REBUILD_SPEC.md` | The full backend contract, if you need to know what a field means. |

---

## 3. First 30 minutes

```bash
git clone <repo> && cd multibot2
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
python3 -m pytest                      # must be 192 passed — this is your baseline
python3 main.py                        # serves on $PORT, default 10000
```

Then capture your golden fixture — **this is how you prove you changed nothing**:

```bash
curl -s localhost:10000/api/dashboard > fixture-before.json
```

Keep it. At the end, `diff` your live payload against it.

---

## 4. The one rule that prevents most failure

> **Nothing recomputes server truth in the browser.**

The server already computes `freshness`, `age_minutes`, `has_trade_levels`,
`actionable`, every `count`, and `signal_summary`. Money formatting and timestamp
rendering **are** your job. Deciding whether a signal is tradeable **is not**.

Recomputing these client-side is the most likely way a UI rebuild silently changes
bot behaviour — the dashboard would agree with itself and disagree with the
Telegram message the user already received.

---

## 5. Build order

### Phase 0 — Freeze
- [ ] Read files 1–4 in full.
- [ ] `python3 -m pytest` → **192 passed**.
- [ ] Screenshot **all 30 combinations × 2 viewports** (1440×900, 390×844).
      This is your visual regression target.
- [ ] Save `fixture-before.json`.

### Phase 1 — Foundations *(no visual change yet)*
- [ ] `ui/tokens.css` — every token from `THEME_SYSTEM.md` §2–§4. Variables only.
- [ ] The 30 theme blocks, **including** both `[data-theme="light"]`-scoped Neo
      fixes and every tuned contrast value.
- [ ] `ui/base.css` — reset, type scale, app shell, bottom nav (76px clearance).
- [ ] Run the contrast test. 0 failures across 30 combos or you have not finished.

### Phase 2 — Primitives
- [ ] Buttons, chips, cards, metric tiles, badges, empty states, modal.
- [ ] Port the **ExpandableControl** contract verbatim.
- [ ] All targets ≥ 32×32. No overflow at either viewport.

### Phase 3 — Pages, one at a time
Order: `overview` → `signals` → `history` → `calendar` → `tools`.
Each is independently shippable. Wire to `/api/dashboard` only;
`/api/calendar` and `/api/backtest` are user-triggered.

### Phase 4 — Accessibility *(not last)*
- [ ] Every interactive element reachable and operable by keyboard alone.
- [ ] **Restore focus after any re-render** — `innerHTML` destroys it.
- [ ] One consolidated live region for polled updates. **Not one per value.**
- [ ] Skip link as the first tab stop, targeting `<main id>`.
- [ ] Status never colour-alone; direction has a shape as well as a hue.
- [ ] Reduced motion honoured.

### Phase 5 — Cutover
- [ ] Register new assets in `main.py`'s `files` dict — **there is no directory
      listing**; an unregistered file 404s.
- [ ] Delete the old CSS/`app.js` only after Phase 4 passes.
- [ ] Update `DESIGN.md` ownership table and `tests/test_dashboard_ui.py`.
- [ ] `diff` your live payload against `fixture-before.json`.

---

## 6. Definition of done

| # | Criterion |
|---|---|
| 1 | `/api/dashboard` unchanged (modulo timestamps) |
| 2 | All 30 combinations render, both viewports |
| 3 | 0 WCAG AA contrast failures |
| 4 | No horizontal overflow |
| 5 | Every target ≥ 24px |
| 6 | Full keyboard operability, focus never lost |
| 7 | Polled updates announced |
| 8 | Exactly one `<h1>` visible |
| 9 | `docs/API.md` still accurate — test green |
| 10 | `python3 -m pytest` fully green |
| 11 | Zero `transition: all` |
| 12 | `node --check` clean on every shipped JS file |
| 13 | Version rendered from the server, never hardcoded |

---

## 7. Non-negotiables

From `LOCKED_RULES.md` §10 — the short version:

- ❌ No real orders, no broker API
- ❌ No provider other than Yahoo
- ❌ Leverage never above 1.0
- ❌ Never signal from an incomplete candle
- ❌ Never recompute freshness / counts / actionability in the UI
- ❌ Never send a signal more than twice
- ❌ Never make SQLite the sole store
- ❌ Never expose `SUPABASE_KEY` to the browser
- ❌ Never rename or remove an API field
- ❌ Never a second source of truth for version or schema

---

## 8. When you get stuck

| Symptom | Most likely cause |
|---|---|
| Page renders nothing, stuck on "CONNECTING", server logs clean | **JS syntax error.** Run `node --check ui/app.js`. See `LESSONS_LEARNED.md` C1. |
| One theme combination looks wrong | A component rule hardcoded a colour. See `THEME_SYSTEM.md` §1. |
| Your theme switch appears to do nothing | You set `dataset.style`; the app reads `localStorage`. See `LESSONS_LEARNED.md` G1. |
| Dashboard works on phone, broken on desktop | Unbalanced CSS brace, usually in a media query. See E2. |
| Contrast test fails on a pair you believe is fake | You added a case that does not exist in the DOM. See D2. |
| Focus jumps to the top after clicking | `innerHTML` re-render. Restore focus by key. See C3. |
