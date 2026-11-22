# Runtime lifecycle audit — 2026-11-22

## Executive finding

The AIC runtime log contains two distinct startup sequences:

- 10:48:14 — scheduler, Telegram polling and MULTIBOT2 startup
- 10:48:52 — the same components announce startup again

Those timestamps establish that the runtime entrypoint was executed twice within roughly 38 seconds. The excerpt alone cannot establish whether AIC restarted the container, briefly overlapped old/new deployment instances, or launched two processes. The old logs did not include process identity, so that distinction was impossible.

The repository audit did find deployment lifecycle drift that needed correction independently of the exact AIC cause.

## Findings and corrections

| Area | Finding | Correction |
|---|---|---|
| Runtime entrypoint | AIC starts `main.py`; Render ran `startup.py && main.py`. | Both now use `python main.py`. |
| Startup announcements | `startup.py` independently sent startup + what's-new messages, while the runtime also owns Telegram. Its persistence text still named Supabase. | `startup.py` is now a compatibility wrapper only. The active runtime sends one startup notice after acquiring leadership. |
| Multiple deployment instances | Every process previously started its own scanner, monitor, summary worker, reminders and Telegram long-polling. | Added an atomic database-backed primary lease in `runtime_leases`. Only its owner starts operational workers. |
| Standby behavior | There was no explicit standby mode. | Non-leaders can serve the dashboard but do not scan, monitor, send startup notices, run reminders or poll Telegram. |
| Worker startup | Threads were started directly with no per-process duplicate guard. | Named worker registry prevents a second live worker with the same name in one process. |
| Process identity | Startup logs did not identify the process. | Boot, worker, leadership, standby and shutdown logs include PID and lease owner. |
| Shutdown | No SIGTERM/SIGINT lifecycle handler released ownership. | Signals set the shared stop event; reminder worker is stopped and the lease is released when possible. |
| Lease failure | A process could keep running workers after losing coordination. | Lease heartbeat failure is fail-closed: operational loops stop and the process shuts down its runtime server. |
| Yahoo failure isolation | An ambiguous empty response for one symbol triggered provider-wide backoff. | Empty responses cool down only that symbol; confirmed rate-limit errors remain provider-wide. |

## Lease contract

- Lease key: `primary`
- Storage: same Turso/libSQL database used by every deployed instance (SQLite for local development/tests only)
- Deployment guard: when `PORT` is set, startup refuses a local-only lease backend unless `MULTIBOT_ALLOW_LOCAL_RUNTIME_LEASE=true` is explicitly set for a single-process test
- TTL: 60 seconds
- Renewal interval: 15 seconds
- Strategy guard verification: at most every 5 seconds (cached between asset/dispatch boundaries to limit remote reads)
- Claim/renew: one atomic SQLite-compatible UPSERT
- Release: owner-qualified delete, so one process cannot release another process's lease
- Failure policy: do not start workers without a lease; stop workers if renewal fails

A crashed process may leave its lease until expiry (up to 60 seconds). A clean SIGTERM/SIGINT drains workers and releases it immediately when they stop. If a worker does not stop within the 45-second shutdown deadline, the lease is deliberately left until expiry. During that interval, a standby process continues serving the dashboard and retries acquisition.

## Deployment contract

AIC Cloud and Render must both run:

```text
python main.py
```

`startup.py` remains only for backward compatibility and delegates to `main.main()`. It must not send messages, initialize a second scheduler, or create its own worker set.

## What this audit does not claim

The code cannot identify the historical cause of the two 10:48 startup sequences because those old logs did not include PID/lease-owner fields. After this change, compare:

- `Runtime process booting | pid=... owner=...`
- `Runtime leadership acquired` (emitted by the leader worker startup log)
- `Runtime standby | pid=... active_owner=...`
- `Runtime leadership lost`
- `Runtime process stopped`

If two processes boot, only one should acquire the lease and start workers. The other should remain in standby.

## Trading safety boundary

No strategy implementation or signal rule is changed by this lifecycle work. Sweep V2 priority, the one-hour freshness gate, completed-candle rules, risk limits and stale-signal rejection remain intact.
