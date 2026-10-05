# Notifications — channels, events and the phone app

Telegram used to be the only transport, hard-wired inside `notification_service.py`.
It is now one of four channel types in `channels.py`. Every channel receives the
same rendered message the Telegram builders already produce, so adding a channel
never touches a strategy, the trade monitor or the scan loop.

## The app

The dashboard installs to a phone home screen and opens standalone:

| File | Served at | Role |
|---|---|---|
| `manifest.webmanifest` | `/manifest.webmanifest` | name, icon, `display: standalone`, `start_url: /dashboard` |
| `sw.js` | `/sw.js` | installability only — it caches **nothing** |
| `app-icon.svg` | `/app-icon.svg` | home-screen icon (maskable) |

Open `/dashboard` on the phone and choose **Add to Home Screen**. The service
worker deliberately does not cache: the dashboard is live paper-trading state and
a cached shell would show stale signals, stale P&L and a frozen scanner.

The Tools → **Notifications** card also has an **Enable browser alerts** button.
That is the browser's own `Notification.requestPermission()` — it is per device
and in-memory only, so it fires while the app is open. Server-side push to a
closed app (Web Push / VAPID) is not wired up yet; it needs a key pair and a
payload-encryption dependency, and it is the next step, not a switch.

## Channels

Configure them in **Tools → Notifications**. A channel is `id`, `type`, `label`,
`target`, `secret`, `enabled` and the list of `events` it subscribes to.

| Type | Target | What is sent |
|---|---|---|
| `telegram` | chat id | `sendMessage`, Markdown (bot token from `TELEGRAM_BOT_TOKEN`) |
| `discord` | webhook URL | `{"content": text}` |
| `slack` | webhook URL | `{"text": text}` |
| `webhook` | http(s) URL | `{"title", "event", "message_type", "text"}` |

Add several Telegram channels with different chat ids to notify more than one
person; add a webhook channel to reach Slack, Discord, n8n, Zapier or your own
receiver.

**With nothing saved, Telegram still works** whenever `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` are in the environment — that is the default from
`channels.default_channels()`. Once a channel *is* saved, the subscription list
is authoritative and an event with no subscriber goes nowhere.

### Targets are credentials

A Discord or Slack webhook URL *is* the token. The dashboard is unauthenticated,
so `GET /api/notifications` never returns a webhook address or an auth secret —
only `has_target` / `has_secret`. **A blank field means "keep what is stored"**:
delete the channel to erase an address, type a new one to replace it.

Channels persist to `notification_channels.json` (git-ignored, overridable with
`NOTIFICATION_CHANNELS_PATH`), machine-local for the same reason as
`bot_settings.json`.

## Events

| Event | Fires from | Default |
|---|---|---|
| `SIGNAL` | `strategy_service.dispatch()` — a BUY/SELL that was sent | on |
| `TRADE_CLOSED` | `trade_monitor.monitor_once()` — SL/TP hit, with P&L and balance | on |
| `REMINDER` | `reminders.ReminderService` — the one allowed second send | on |
| `STALE` | `strategy_service.dispatch()` — a directional signal older than 1 hour | on |
| `SCAN` | `main.run_strategy_cycle()` — a clean scan finished | on |
| `ERROR` | `main.run_strategy_cycle()` — a scan finished with errors | on |
| `SUMMARY` | `main.summary_loop()` — daily and weekly | on |

`SCAN` runs every few minutes per strategy, so a channel that wants quiet only
needs to untick it. `SUMMARY` is sent once per calendar day at `SUMMARY_DAILY_HOUR`
(default `18`, IST) and additionally on `SUMMARY_WEEKLY_DAY` (default `6`,
Sunday, using Python's Monday=0 convention). The watermark lives in
`notification_summary_state.json` (`SUMMARY_STATE_PATH`), so a restart does not
re-send a summary that already went out.

## Delivery contract

`NotificationService.deliver()` records a `PENDING` row per channel, sends,
records `SENT`/`FAILED`, and retries a `FAILED` channel on its own exponential
backoff (`2 ** retry_count` minutes, `MAX_RETRIES = 3`). A retry targets the
channel that failed, never the whole fan-out again, so a healthy channel is not
sent a duplicate. `deliver()` returns True when *any* channel accepted the
message.

`SCAN`, `ERROR` and `SUMMARY` are sent with `audit=False`: they have no
`signal_events` row and `signal_deliveries.signal_id` is a foreign key into that
table in Supabase. The `STALE` warning is also unaudited — the durable
`NOT_SENT_STALE` row is what the dashboard reports for that signal, and a failed
warning attempt must not overwrite it.

## Tests

`tests/test_notification_channels.py` covers the registry, the redaction
round-trip, the fan-out, the per-channel retry and the installable-app contract.
`tests/test_notification_service.py` still pins the original guarantee: a
delivery-audit failure must never turn an accepted message into a failure.

## Environment

| Key | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram transport (default channel) |
| `NOTIFICATION_CHANNELS_PATH` | where channels are saved |
| `SUMMARY_STATE_PATH` | daily/weekly watermark file |
| `SUMMARY_DAILY_HOUR` / `SUMMARY_WEEKLY_DAY` | when the summaries go out (IST hour, Monday=0 weekday) |
