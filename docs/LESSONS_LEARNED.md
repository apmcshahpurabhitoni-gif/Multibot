# Lessons Learned — MULTIBOT2

Every defect found in this repository, what actually caused it, and what now stops
it from happening again. **Read this before writing any code in a new build.**

Each entry is: **what** → **why it survived** → **the guard now in place**.

---

## Category A — Silent data loss

### A1. `supabase/schema.sql` never created two tables `db.py` writes to
**What.** The root `schema.sql` and `supabase/schema.sql` were independent copies
that drifted. The Supabase copy omitted `scan_runs` and `market_data_cache`.
**Why it survived.** `db.py` catches `PGRST205` (missing table) and degrades to
SQLite with a *warning*. The bot kept running perfectly. A fresh database
provisioned from that file would have silently lost scan history and the durable
Yahoo cache — no error, just missing data.
**Guard.** `tests/test_schema_parity.py` parses `db.py` for every
`_supabase_request("METHOD","table")` call and asserts both schema files create
all of them. Mutation-tested: reverting the fix fails 3 tests.

> **Lesson.** A defensive fallback that *recovers* is also a fallback that *hides*.
> If a code path can fail open, add a test that asserts the precondition, not just
> the recovery.

### A2. `dashboard_signal()` could 500 the entire dashboard
**What.** The degradation guard wrapped `signal_status()` but left
`pd.Timestamp(event["timestamp"])` one line above it, unguarded. An unparseable
timestamp raised `DateParseError` and took down the whole `/api/dashboard`
response.
**Why it survived.** Postgres enforces `timestamptz`, so the bad value could only
enter through the **SQLite fallback**, which stores `timestamp` as free-form
`TEXT`. The comment on the except block said "One malformed historical row must
never 500 the entire dashboard API" — the comment was describing an intent the
code did not fully implement.
**Guard.** The parse now sits inside the guard; `test_api_contract.py` asserts a
malformed row degrades to `STALE` rather than raising.

> **Lesson.** A guard that covers *most* of a function is worse than no guard,
> because it reads as protection. Cover the whole failure surface or write no
> comment claiming you do.

## Category B — Contracts that did not exist

### B1. No API contract at all
**What.** `main.py` hand-rolls routing inline. The only record of the payload
shape was the minified rendering code in `app.js`.
**Why it survived.** There was one consumer, so the contract never had to be
written down — until someone wanted to replace that consumer.
**Guard.** `docs/API.md` + `tests/test_api_contract.py`, which asserts the
envelope has every documented key **and no undocumented ones**.

### B2. Two divergent `schema.sql` files
Covered in A1. The general rule: **one canonical artefact, one mirror, one test.**

### B3. `startup.py` missing from `pyproject.toml` `py-modules`
**What.** 23 of 24 root modules were declared. `render.yaml` runs
`python startup.py && python main.py`, so a wheel install would not have shipped
the entrypoint.
**Why it survived.** CI installs with `pip install -e .`, where an editable install
sees the source tree directly and the omission is invisible. **Only a real
wheel/sdist build would have caught it.**
**Guard.** `tests/test_rebuild_spec_inventory.py` asserts `py-modules` equals the
root `*.py` set exactly.

### B4. `AI_REBUILD_SPEC.md` §25 listed 17 of 24 modules
**What.** It also omitted `strategies/engulfing_66_sma/` entirely — the document
called "complete AI reconstruction contract" would have produced a bot with 2 of 3
strategies and no news, calendar or reminders.
**Why it survived.** Nobody diffed the spec against the filesystem.
**Guard.** The spec is now a full grouped inventory, plus §30 strategy inventory,
asserted against the live registry.

## Category C — Frontend defects that shipped silently

### C1. `app.js` stopped parsing and the dashboard went dead
**What.** A one-line edit inserted before `async function loadDashboard`, anchored
on the substring `function loadDashboard(){try{`. The match consumed the `async`
keyword, leaving `await` in a non-async function — `SyntaxError`.
**Why it survived.** **No bundler, no linter, no build step, no console capture in
CI.** The whole file failed to execute: no render, page stuck on "CONNECTING", and
the *server* logs were perfectly clean because the server was never at fault.
**Guard.** `tests/test_frontend_syntax.py` runs `node --check` over every shipped
asset (skips if node is absent) and separately asserts the `async` keyword is
intact. Mutation-tested.

> **Lesson — the most important one here.** **Never edit a shipped static
> JavaScript file without running `node --check` on it.** A syntax error in
> unbundled JS is a total, silent, server-side-invisible outage. Do it in the same
> command as the edit.

### C2. Card rows were mouse-only
**What.** `.card-body` / `.card-main` was a `<div data-expand>` handled by a
delegated click listener. 8 bodies, **0 focusable** — a WCAG 2.1.1 failure.
**Why it survived.** The adjacent `.expand-button` *was* a real button with
`aria-expanded` and worked correctly, so a mouse-only spot check passed.
**Guard.** The row is now the single composite control (`role="button"`,
`tabindex="0"`, key handling, focus restored after re-render); the inner button is
`tabindex="-1"`.

### C3. Focus was destroyed by every re-render
**What.** The dashboard re-renders lists via `innerHTML` every 30 seconds and on
every toggle, which detaches the focused node and drops focus to `<body>`.
**Why it survived.** Invisible to mouse users; only a keyboard walkthrough finds it.
**Guard.** Card rows re-find themselves by key after toggle and re-focus.
**Still open:** date-group toggles, history rows and calendar groups have the same
problem.

### C4. Eleven polled values were silent to screen readers
`systemStatus`, `versionBadge`, `overviewTotalPnl`, `overviewTradeCount`,
`overviewSignalCount`, `scanSummary`, `signalsResultCount`, `historyResultCount`,
`historyClosedCount`, `equityCurveValue`, `heroStatus`.
**Fix.** One consolidated `#dashboardAnnouncer` live region.
**Note.** The wrong fix is 11 live regions — that would interrupt 11 times every
30 seconds. **Consolidate.**

## Category D — Contrast and the test that missed it

### D1. 142 WCAG AA failures across 30 combinations
Tokens chosen for hue rather than legibility. Fixed at v3.3.0 by darkening until
each clears 4.6:1 against its composited background.

### D2. The contrast test composited washes over `--surface` only
**What.** Wash tokens are semi-transparent and are painted over **`--surface-2`**
in two real DOM paths: `.card-main:hover` repaints the row with `--surface-2`
while `.signal-side` keeps its buy/sell wash, and `.fresh`/`.stale` live inside
`.detail-grid>div`, which paints `--surface-2`.
**Consequence.** Nine genuine AA failures shipped through a test that reported zero:
neo light `--negative` at **3.95:1**, and four `--accent-strong` values at
4.38–4.49:1.
**Guard.** `test_contrast_tokens.py` now checks both surfaces, with a comment
naming the two DOM paths. `--surface-3` is deliberately **excluded** — it is only
used by the scrollbar thumb, so a wash over it is a phantom.

> **Lesson.** A test that enumerates a *plausible* matrix will eventually catch a
> phantom and teach you to ignore it. **Before adding a case, prove the
> combination exists in the DOM** — otherwise you will "fix" tokens for a state
> that never renders.

## Category E — CSS architecture

### E1. The three-sheet override cascade is self-repairing, and that is the problem
`styles.css` → `foundation.css` → `appearance-overrides.css`. `DESIGN.md` records
that rules past ~50 KB became unreachable and had to be "corrected from the
appearance layer" — which is how `appearance-overrides.css` grew to 84 KB of
patch-on-patch.
**Fix in a rebuild.** Ordered layers, **zero overrides**:
`tokens.css` → `base.css` → `components.css` → `themes.css`.

### E2. An unclosed brace silently ate 200 lines
`foundation.css` never closed its History `max-width:560px` media query, so the
canonical `.collapse-control` and date-group rules were swallowed. Phones looked
correct because the smaller queries re-supplied the same geometry; desktop rendered
an empty `14x4` box with no chevron.
**Lesson.** Verify CSS changes at **desktop as well as mobile**. A mobile-only
check hides an unbalanced-brace bug perfectly.

### E3. Emoji as an icon system
Platform-dependent rendering, no independent sizing, breaks `line-height`, and some
are announced by screen readers. See [`DESIGN_SYSTEM/icons.md`](DESIGN_SYSTEM/icons.md).

## Category F — Concurrency

### F1. `LOCK` was declared and never used
`main.py` declared `LOCK = threading.RLock()` and then mutated `LAST_PING_AT`
(WMPI request thread vs. health request thread) and `NEWS_PAUSE_ENABLED` +
`NEWS_GATE.enabled` (Telegram polling thread vs. scheduler) without it. The
`/newspause` case is a read-modify-write, so two commands could interleave.
**Fix.** All mutations now happen under `LOCK`, and `/api/health` reads a locked
snapshot.
**Guard.** `tests/test_keepalive_health.py` asserts both the guarded write and the
guarded read. Mutation-tested.

> **Lesson.** An unused lock reads as "thread safety handled". If you declare it,
> use it everywhere, or delete it.

## Category G — Process and tooling

### G1. The theme sweep reported confident, wrong results
A contrast sweep that set `dataset.style` and measured in *separate* browser calls
reported "0 failures" while actually rendering `modern` thirty times. Three
compounding causes:
1. `app.js::initAppearance()` reads **`localStorage`** and overwrites
   `dataset.style` on every bootstrap — the attribute is not the source of truth.
2. The 30-second poll re-renders between calls.
3. The first `eval` landed before `DOMContentLoaded`.
**Fix.** Switch via `localStorage` + reload, and **set and measure in a single
atomic `eval`**.

> **Lesson — verify the measuring instrument before trusting the measurement.**
> Always assert the tool actually applied what you asked for before believing a
> clean result.

### G2. `app.js` and `pyproject.toml` drifted from reality with nothing to notice
Editing reach limits, editable install masking packaging bugs, and source-string
tests that encoded the *buggy* form (`assert '"last_ping_at":LAST_PING_AT'` passed
only because the code read an unguarded global). **Tests that assert source text
must be written against the contract, not the current implementation.**

### G3. ~26MB of vendored agent tooling was committed and then not ignored
`.agents/`, `.claude/`, `agent/` and `skills-lock.json` — 71 files tracked, 26MB
more untracked and invisible to `.gitignore`. Worse, `/architecture` served from
`agent/skills/archify/`, so untracking naively would have 404'd a live route.
**Fix.** The two first-party architecture artefacts were relocated to
`docs/architecture/`, `main.py` updated, then the whole tree untracked with
`git rm --cached` (files kept on disk).

### G4. Tests that cannot fail
Every new guard here was mutation-tested — revert the fix, confirm the failure.
Two guards written this session were themselves wrong on first run (one asserted
`"function loadDashboard(){try{" not in source`, which is a substring of the valid
`async function loadDashboard(){try{`). A test that passes on the broken state is
worse than no test because it manufactures confidence.

### G5. Stale audit artefacts are not documentation
`DASHBOARD_AUDIT_FRESH.txt` still claims `WHATS_NEW.md` is v3.2.8 (now v3.3.0).
Dated audit records are **history, not specification**. Pin them to a revision in
the filename and never let them be cited as current.

### G6. The deliverable was built, verified, and then hidden
`multibot2-ai-rebuild-kit.zip` was created, integrity-checked and round-trip
extracted — and then added to `.gitignore` in the same session. An ignored file
never appears in the Changes panel, so a requested deliverable simply did not
exist as far as the user could tell. **A "generated artefact" is not the same as
"a thing nobody asked for."** If a file was requested by name, it stays
committable, and the recipe that regenerates it is documented next to it.

### G7. A copy of a package tree was flattened into files
The kit shipped `reference/strategies/adaptive_trend.py`. The repo has
`strategies/adaptive_trend/strategy.py` — a package. The bytes were identical, so
`zipfile.testzip()` passed, the round-trip extract passed, and the file count
looked right. But an agent rebuilding from the kit would have produced a strategy
layout that `registry.discover_strategies()` cannot find.
**Fix.** `reference/strategies/` is now a byte-identical `cp -r` of the repo
package tree, and `tests/test_rebuild_kit.py` asserts the layout by name.
The same test caught a second silent defect: the four reference contracts
(`AI_REBUILD_SPEC.md`, `AI_CONTEXT.md`, `STRATEGY_DEVELOPER_GUIDE.md`,
`DESIGN.md`) live at the **repo root**, not under `docs/`, so the first recipe
copied them from a directory where they do not exist and dropped all four.
**Copy source paths are part of the contract.** Verify with `diff -r` and
`cmp`, never with "the zip opened fine".

## Category H — Still open

| # | Item |
|---|---|
| H1 | `main.py` writes `Cache-Control: no-store` on every static asset — correct, but it means a browser re-downloads ~324KB of CSS every load |
| H2 | Date-group toggles, history rows and calendar groups still lose focus on re-render |
| H3 | `--surface-2` is not always `<div class="detail-grid">`'s parent; audit any new nesting |
| H4 | Local Python is 3.10 while `requires-python = ">=3.11"`; CI is the only representative run |
| H5 | `Workers Builds: multibot` fails on every PR and cannot be fixed from this repo — no Worker config exists |
