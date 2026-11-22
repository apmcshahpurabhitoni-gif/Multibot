# Turso / libSQL Reliability Repair Plan

**Status:** Plan recorded before implementation  
**Base branch:** `main`  
**Base commit:** `1173884019bb986f4860b990a9cf0d9cedec1ae1`  
**Working branch:** `fix/turso-transaction-reliability-20261123`  
**Scope:** Repair database transaction handling and error classification without changing trading rules.

## 1. Evidence and diagnosis

The production logs repeatedly show this error at the libSQL/Hrana commit boundary:

```
interactive transaction was rolled back because the stream was idle for too long
SQLITE_BUSY
```

The same deployment also reports successful remote-cache health checks and successful scanner cycles between failures. This is evidence of intermittent transaction/operation failures, not proof that the entire Turso service is offline.

The current code has several concrete weaknesses:

- `_RemoteConnection.__exit__()` commits every successful context, while a number of methods also call `commit()` explicitly. This can issue redundant commits on one connection.
- The retry helper is limited to market-data cache operations and runtime lease acquisition. Scan-run writes and several other idempotent state writes do not use it.
- `run_strategy_cycle()` writes the RUNNING scan row before entering its scan exception handler. A persistence error aborts the cycle before scanning.
- `StrategyService.scan_and_dispatch()` catches broad exceptions and labels them `MARKET_DATA_ERROR`, including failures that may originate in database/cache persistence.
- Calendar cache writes use direct connections and commits instead of the shared retry policy.

## 2. File-by-file implementation plan (dependency order)

### A. `db.py` — core transaction and retry contract (first)

**Changes planned**
1. Make the remote connection adapter commit only when a write transaction is pending; do not perform an unnecessary second commit after an explicit commit.
2. Preserve the original operation/commit exception if rollback also fails, and always close failed connections.
3. Consolidate transient-error detection for Hrana `SQLITE_BUSY`, idle-stream rollback, and known transport failures.
4. Provide a narrowly scoped retry helper that opens a fresh connection for every attempt and retries only operations proven idempotent.
5. Add safe retries for scan-run upserts and other deterministic upserts/sets/deletes where replay cannot duplicate side effects.
6. Keep append-only delivery inserts, incrementing counters, Telegram send-state transitions, and other ambiguous non-idempotent writes out of blind retry.
7. Improve database health reporting so connectivity and write capability are not represented by the same weak `SELECT 1` check.

**Compatibility constraints**
- Preserve SQLite local-development behavior.
- Preserve all existing tables, columns, indexes, migration behavior and public method signatures unless tests prove a change is necessary.
- Do not change the Turso URL/token configuration or upgrade the pinned libsql package as part of this repair.

### B. `calendar_store.py` — use the shared database policy (second)

**Changes planned**
- Route calendar cache/attempt upserts through the shared safe-retry boundary, using a new connection for each retry.
- Keep calendar rows and the market-data cache mirror consistent with current keys and payload formats.
- Do not retry any append-only operation or silently swallow a final persistence failure.

### C. `strategy_service.py` — classify database failures correctly (third)

**Changes planned**
- Treat typed database failures as database failures, not Yahoo/market-data failures.
- Preserve existing strict market-data diagnostics for genuine provider/candle errors.
- Let persistent database failures reach the runtime scan-cycle boundary rather than fabricating a `MARKET_DATA_ERROR` signal.
- Preserve runtime leadership fail-closed behavior and Telegram/trade ordering.

### D. `main.py` — make scan-run persistence safe around trading (fourth)

**Changes planned**
- Keep the initial RUNNING record as a prerequisite for a live scan: if it cannot be durably recorded after bounded retries, do not start a scan that cannot be audited.
- Handle a final scan-history write failure separately after the scan has already run; log it as a persistence failure and do not replay the scan or resend notifications/trades merely because history finalization failed.
- Include database failures in operational diagnostics without misreporting them as market-data errors.
- Leave lease election, HTTP serving, scheduler intervals, and worker lifecycle unchanged unless a regression test demonstrates a dependency.

### E. Tests — verify behavior in dependency order (last)

1. `tests/test_turso_database.py`
   - Reproduce the Hrana idle-stream/SQLITE_BUSY error at execute and commit boundaries.
   - Verify retry attempts use fresh connections and close failed connections.
   - Verify idempotent scan-run upserts do not create duplicate rows.
   - Verify non-idempotent delivery/counter operations are not blindly retried.
   - Verify explicit commit plus context exit does not issue a second commit.
   - Verify local SQLite behavior and calendar persistence remain compatible.
2. `tests/test_runtime_lifecycle.py`
   - Verify typed SQL errors preserve the Hrana detail through the remote adapter.
3. `tests/test_sweep_market_data_errors.py`
   - Confirm real market-data failures retain their current diagnostics.
   - Confirm a typed database failure is not converted into a market-data error signal.
4. `tests/test_main.py`
   - Confirm failure to persist the initial RUNNING row prevents trading.
   - Confirm failure to persist the final row does not replay a completed scan or duplicate Telegram/trade side effects.
5. Run the full existing test suite and schema-parity checks.

## 3. Files intentionally not planned for modification

- `yahoo_provider.py`: it already calls the database cache methods, which are the correct place to own retry behavior.
- `requirements.txt`: keep `libsql==0.1.11` until a reproducible compatibility issue proves an upgrade is required.
- `schema.sql` and `supabase/schema.sql`: no schema change is indicated by the current error.
- Strategy modules, strategy manifests, Sweep V2/ICT logic, asset universe, freshness rules, risk settings and paper-trading configuration.

## 4. Safety rules

- Never retry a Telegram send or append-only delivery insert based only on an ambiguous commit result.
- Never retry an increment operation unless it is made idempotent with a stable operation key.
- Never continue live trading if the initial scan-run record cannot be made durable.
- Never replay a completed scan because only its final history update failed.
- Do not disable or weaken runtime lease checks.
- Do not alter strategy signal conditions, indicators, targets, stops, risk sizing or asset lists.

## 5. Acceptance criteria

The repair is complete only when:

- The exact Hrana `SQLITE_BUSY` failure is covered by deterministic regression tests.
- Safe database operations retry with bounded backoff and fresh connections.
- Non-idempotent operations are not duplicated by retry.
- The adapter does not redundantly commit a completed transaction.
- Database errors are distinguishable from Yahoo/market-data errors.
- A scan cannot trade without its initial durable scan record.
- A final history-write failure cannot trigger duplicate trading or Telegram actions.
- Existing strategy, market-session, runtime-lease, dashboard and schema tests pass.
- The implementation is delivered as one cohesive code commit on this working branch; no deployment or merge to `main` occurs without a separate explicit step.

## 6. Execution sequence

Implement A → B → C → D, then add/run E. Review the final diff against the base commit, verify only the planned files changed, and report test results and any remaining limitations. Do not deploy automatically.
