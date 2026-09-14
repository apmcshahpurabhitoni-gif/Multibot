# Senior Ponytail Consistency Audit — MULTIBOT2 v3.2.6

## Scope

This pass fixes the connected dashboard/runtime defects as one contract-first change. It does not change trading strategy logic, locked risk rules, asset universe, market-data provider, Telegram transport or paper-only mode.

## Contract decisions

### Live signals
Runtime lifecycle events only. A live signal is directional BUY/SELL data with explicit freshness and pipeline state.

### History
Completed paper trades only.

### Backtest trades
Simulated completed trades for the selected strategy, asset and period only.

### Backtest signals
Directional signals generated during that selected backtest only. They are not live runtime opportunities.

## Fixes

1. **Safe API parsing**
   - Dashboard, Calendar and Backtest readers inspect response text before parsing.
   - Empty, malformed and non-JSON responses now become explicit UI errors.
   - Backtest failures hide the result workspace so stale results cannot look current.

2. **Canonical signal levels**
   - Entry, stop loss and take profit are persisted with each signal lifecycle event.
   - Dashboard reads those same facts from canonical persistence.
   - Older records without levels are explicitly non-actionable diagnostics.

3. **Signal presentation**
   - Missing levels no longer render as `Entry — · Target — · Stop —`.
   - Lifecycle and actionability are separate concepts.
   - BUY/SELL remains direction; P/L remains trade outcome.

4. **Backtest semantics**
   - `Detected opportunities` was replaced with `Backtest signals` / `Signals generated during this test`.
   - Backtest signal rows can show complete levels when the strategy supplied them.

5. **Bounded mobile panels**
   - Completed backtest trades use a fixed maximum height and internal touch scrolling.
   - Backtest signals use the same contained-panel behavior.
   - Final CSS declarations override older merge-era rules that accidentally unbounded lists.
   - Mobile content reserves safe-area space for bottom navigation.

6. **Documentation and release consistency**
   - `release_notes.py` remains the single source of truth.
   - Dashboard, Telegram, README and WHATS_NEW.md use the canonical release highlights.
   - AI_CONTEXT.md documents the current semantic and API contracts.

## Verification

Run from repository root:

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python tools/check_release_docs.py
node --check app.js
python -m py_compile main.py dashboard.py db.py signal_lifecycle.py
```

The v3.2.6 audit pass was verified with the full repository test suite plus JavaScript and Python syntax checks.
