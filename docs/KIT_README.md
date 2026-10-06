# MULTIBOT2 — AI Rebuild Starter Kit

Everything an AI agent needs to rebuild the dashboard UI with a new, good-looking
interface while **keeping all 30 theme combinations** and **changing zero bot
behaviour**.

Generated from the live repository. Version **3.5.0**.

---

## Start here

**→ [`docs/START_HERE.md`](docs/START_HERE.md)**

It gives the read order, the commands to run first, the phased build plan, the
definition of done, and a troubleshooting table for the failures you are most
likely to hit.

---

## What is in here

### `docs/` — the contracts
| File | What it gives you |
|---|---|
| `START_HERE.md` | **Read this first.** Read order, first commands, build phases, done criteria, troubleshooting. |
| `API.md` | Every endpoint, full payload schemas, the 11 computed signal fields, the `actionable` predicate, client render helpers. **You cannot start without this.** |
| `THEME_SYSTEM.md` | How 3 styles × 5 accents × 2 themes = 30 combinations work; the two-layer token rule; the tuned values that must not be reverted. |
| `LOCKED_RULES.md` | The 11 invariants you may not change, and the 10 things a rebuild must never do. |
| `REBUILD_BRIEF.md` | The master brief: all layers, 7 anti-patterns to avoid, 6-phase plan, 13 acceptance criteria, risk table. |
| `LESSONS_LEARNED.md` | **Every defect this project has shipped**, its root cause, and the guard that now prevents it. Do not rediscover these. |
| `DESIGN_SYSTEM/geometry.md` | Spacing scale, the 3 radius tiers, control sizes, breakpoints, nav clearance. |
| `DESIGN_SYSTEM/type.md` | Font stacks, the real type scale, `tabular-nums` rule, the sub-11px defect. |
| `DESIGN_SYSTEM/components.md` | ~124 components grouped, with states and a11y contracts. |
| `DESIGN_SYSTEM/motion.md` | Durations, easings, reduced-motion, and why nothing may animate on the 30s poll. |
| `DESIGN_SYSTEM/icons.md` | The emoji problem and the inline-SVG-sprite recommendation. |
| `DESIGN_SYSTEM/validation.md` | The reproducible 30-combination × 2-viewport check. |

### `reference/` — the backend you are NOT rewriting
`AI_REBUILD_SPEC.md` (full contract, §1–30) · `AI_CONTEXT.md` (orientation) ·
`STRATEGY_DEVELOPER_GUIDE.md` · `DESIGN.md` (current UI ownership) ·
`MANIFEST.txt` · `schema.sql` (canonical DDL) · `render.yaml` (deploy) ·
`pyproject.toml` (deps, version) · `strategies/` (the strategy contract).

`reference/strategies/` is a **byte-identical copy of the repo's `strategies/`
package** — same directory layout, not flattened. Each strategy is a package
(`strategies/<id>/__init__.py` + `strategy.py`), with the shared contract in
`strategies/base.py` and discovery in `strategies/registry.py`.

> **Do not flatten it to `strategies/<id>.py`.** An earlier build of this kit
> shipped renamed flat copies; content was correct but the implied file layout
> was wrong, and a rebuild from it would have produced a repo whose strategy
> files do not match `registry.discover_strategies()`.

### `guards/` — copy these into your new project
| Test | Stops |
|---|---|
| `test_api_contract.py` | Server and docs drifting apart; undocumented payload keys |
| `test_schema_parity.py` | The two schema files drifting (this bug cost scan history) |
| `test_rebuild_spec_inventory.py` | Docs omitting modules/strategies; packaging drift |
| `test_contrast_tokens.py` | WCAG AA regressions across all 30 combinations |
| `test_frontend_syntax.py` | A silent JS parse error that kills the whole dashboard |
| `test_keepalive_health.py` | Shared state mutated without the lock |
| `test_no_wall_clock_dependence.py` | **Tests that fail on a date instead of on a change.** A hardcoded event timestamp judged against the real clock stops passing when real time crosses it. |
| `test_rebuild_kit.py` | **This kit going stale or silently losing files.** Zip integrity cannot see a flattened `strategies/` tree or four reference contracts copied from the wrong directory. |

> **Mutation-test every guard you copy.** Revert the fix it protects and confirm
> it fails. A test that passes on the broken state is worse than no test — it
> manufactures confidence. See `LESSONS_LEARNED.md` G4.

---

## Rebuilding this kit

The kit is a copy of tracked repo files — it has no build step of its own.
**Editing any file that ships in the kit invalidates it**, and
`tests/test_rebuild_kit.py` will fail until you rebuild. That is intentional:
a stale kit is worse than a missing one.

From the repository root:

```bash
KIT=/tmp/multibot2-ai-rebuild-kit
rm -rf "$KIT" && mkdir -p "$KIT"/{docs,guards,reference}

cp docs/KIT_README.md "$KIT/README.md"
cp docs/API.md docs/THEME_SYSTEM.md docs/LOCKED_RULES.md docs/REBUILD_BRIEF.md \
   docs/LESSONS_LEARNED.md docs/START_HERE.md "$KIT/docs/"
cp -r docs/DESIGN_SYSTEM "$KIT/docs/DESIGN_SYSTEM"
cp AI_REBUILD_SPEC.md AI_CONTEXT.md STRATEGY_DEVELOPER_GUIDE.md DESIGN.md "$KIT/reference/"
cp MANIFEST.txt schema.sql render.yaml pyproject.toml "$KIT/reference/"

for t in api_contract contrast_tokens frontend_syntax keepalive_health \
         no_wall_clock_dependence rebuild_kit rebuild_spec_inventory schema_parity; do
  cp "tests/test_${t}.py" "$KIT/guards/"
done

# strategies/ is copied as a package tree; never flatten it.
mkdir -p "$KIT/reference/strategies"
cp strategies/__init__.py strategies/base.py strategies/registry.py "$KIT/reference/strategies/"
for d in adaptive_trend engulfing_66_sma sweep_v2 _template; do
  mkdir -p "$KIT/reference/strategies/$d"
  cp "strategies/$d/__init__.py" "strategies/$d/strategy.py" "$KIT/reference/strategies/$d/" \
     2>/dev/null || cp "strategies/$d/strategy.py" "$KIT/reference/strategies/$d/"
done

# docs/architecture/ is deliberately excluded: 819KB of generated HTML,
# not a rebuild input. The four reference docs above live at the repo ROOT,
# not under docs/ — copying them from docs/ silently produces a kit with four
# missing contracts and no error.
rm -f multibot2-ai-rebuild-kit.zip
python3 -m zipfile -c multibot2-ai-rebuild-kit.zip "$KIT"
```

Verify before shipping — an unverified kit is worse than none:

```bash
python3 -c "import zipfile;print(zipfile.ZipFile('multibot2-ai-rebuild-kit.zip').testzip() or 'OK')"
rm -rf /tmp/kit_check && mkdir /tmp/kit_check
python3 -m zipfile -e multibot2-ai-rebuild-kit.zip /tmp/kit_check
diff -r strategies /tmp/kit_check/multibot2-ai-rebuild-kit/reference/strategies \
     -x '__pycache__' -x 'tests' -x '*.pyc'      # must be silent
cmp docs/KIT_README.md /tmp/kit_check/multibot2-ai-rebuild-kit/README.md
```

`diff -r` is the check that catches a flattened or stale `strategies/` tree.
Zip integrity alone does not. Expect **39 files**: 1 README + 12 docs +
8 guards + 18 reference (4 contracts + 4 deploy/manifest files + 10 strategy
package files). `tests/test_rebuild_kit.py` runs exactly these checks for you.

---

## The one rule

> **Nothing recomputes server truth in the browser.**

The server already computes `freshness`, `age_minutes`, `has_trade_levels`,
`actionable`, every `count`, and `signal_summary`. Money formatting and timestamp
rendering are your job. **Deciding whether a signal is tradeable is not.**

This is the single most likely way a UI rebuild silently changes bot behaviour.

---

## Three things to check before you trust any tooling

1. **Set and measure a theme in ONE browser call.** `app.js` reads `localStorage`
   and overwrites `dataset.style` on every bootstrap. A sweep that sets the
   attribute separately will measure `modern` thirty times and report a confident,
   wrong result.
2. **Run `node --check` on every JS file you ship.** No bundler, no linter — a
   syntax error is a total, silent, server-invisible outage.
3. **Prove a contrast case exists in the DOM before "fixing" it.** A phantom case
   teaches you to ignore the test.

Details and the full list: [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md).

---

## Non-negotiables

Paper trading only · Yahoo Finance only · 25 assets · ₹100,000 account ·
₹2,000 risk per trade · **1.0× leverage never higher** · freshness **exactly**
1 hour · **max 2 sends** per signal identity · Supabase authoritative with SQLite
fallback · signals on completed candles only.

Full list: [`docs/LOCKED_RULES.md`](docs/LOCKED_RULES.md).
