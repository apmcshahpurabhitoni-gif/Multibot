"""One owner for delivery, persistence and bounded retry across every channel.

Telegram used to be the only transport, inlined here. The transport is now a
value read from `channels.py`: this service fans one message out to every
enabled channel subscribed to the event, records an independent delivery row per
channel, and retries each one on its own schedule. Every existing caller --
strategies, the trade monitor, reminders, the scan loop -- still call
`deliver()` and know nothing about the fan-out.

"No channel succeeded" is the failure the strategy layer acts on, so `deliver()`
returns True when *any* channel accepted the message. One channel being down
never hides a copy the operator did receive; the failed channel is audited and
picked up by `retry_failed()`.
"""
from __future__ import annotations

import logging

import pandas as pd

import channels as channel_registry
from config import IST_TIMEZONE
from telegram import TelegramConfig, TelegramMessage, send_message

logger = logging.getLogger("multibot2.notification")


class NotificationService:
    MAX_RETRIES = 3

    _silent_reasons = frozenset({
        "STALE_SIGNAL",
        "NO_DIRECTIONAL_SIGNAL",
        "MARKET_DATA_ERROR",
    })
    _silent_statuses = frozenset({
        "NON_DIRECTIONAL",
        "STALE",
        "DUPLICATE_LIMIT",
        "REMINDER_PENDING",
        "ACCOUNT_LIMIT",
        "NO_TRADE_PLAN",
        "DELIVERY_FAILED",
        "DELIVERED",
        "ERROR",
    })

    def __init__(self, database, telegram_config=None):
        self.database = database
        self.telegram_config = telegram_config

    def _config(self):
        if getattr(self, "_config_value", None) is not None:
            return self._config_value
        return self.telegram_config or TelegramConfig.from_env()

    def _should_silence(self, *, signal_id):
        lookup = getattr(self.database, "signal_event", None)
        if lookup is None:
            # The database does not expose signal events (minimal test fakes and
            # embedders): the gate cannot reason about the signal, so default to
            # delivering rather than muting the operator's chat.
            return False
        try:
            row = lookup(signal_id)
        except Exception as exc:
            logger.debug("notification silence check skipped for %s: %s", signal_id, exc)
            return True
        if row is None:
            return True
        reason = row.get("reason")
        status = row.get("pipeline_status")
        if reason in self._silent_reasons:
            return True
        if status in self._silent_statuses:
            return True
        return False

    def _implicit_telegram(self):
        return {
            "id": "telegram",
            "type": "telegram",
            "label": "Telegram",
            "target": "",
            "enabled": True,
            "events": list(channel_registry.DEFAULT_EVENT_SUBSCRIPTIONS),
            "secret": "",
        }

    def _targets(self, kind):
        """Channels that should receive this event.

        With nothing configured the original single-transport behaviour holds, so
        an unconfigured deployment keeps delivering over Telegram for the events a
        fresh bot sends to chat (DEFAULT_EVENT_SUBSCRIPTIONS, which deliberately
        excludes SCAN). Once channels are configured the subscription list is
        authoritative: an event with no subscriber is not sent anywhere.

        SCAN never falls back to the implicit Telegram channel in either branch:
        the scanner posts on every sweep, so an unconditional fallback is what
        spammed the chat with a "Scan complete" bubble every interval. Operators
        who want it subscribe a channel to SCAN in Tools.
        """
        configured = channel_registry.load()
        if not configured:
            implicit = self._implicit_telegram()
            return [implicit] if kind in implicit["events"] else []
        return [c for c in configured if c["enabled"] and kind in c["events"]]

    def _audit(self, signal_id, channel_id, status, message, metadata, error=None):
        try:
            self.database.record_delivery(
                signal_id,
                channel=channel_id,
                status=status,
                error_text=error,
                message_type=message.message_type,
                metadata=metadata,
            )
        except Exception as exc:
            logger.warning("Delivery audit skipped for %s/%s: %s", signal_id, channel_id, exc)

    def _send(self, channel, message, kind):
        if channel["type"] == "telegram":
            if getattr(self, "_telegram_send", None) is not None:
                result = self._telegram_send(message, self._config())
                return bool(result)
            return send_message(message, self._config())
        return channel_registry.send(channel, message, kind)

    def _deliver_one(self, channel, *, signal_id, message, kind, metadata, audit=True):
        base = dict(metadata or {})
        base.update({"kind": kind, "text": message.text, "channel": channel["id"]})
        if audit:
            self._audit(signal_id, channel["id"], "PENDING", message, base)

        try:
            self._send(channel, message, kind)
        except Exception as exc:
            retry_count = int(base.get("retry_count", 0)) + 1
            status = "PERMANENT_FAILURE" if retry_count >= self.MAX_RETRIES else "FAILED"
            base["retry_count"] = retry_count
            if status == "FAILED":
                base["next_retry_at"] = (
                    pd.Timestamp.now(tz=IST_TIMEZONE) + pd.Timedelta(minutes=2 ** retry_count)
                ).isoformat()
            logger.warning(
                "Notification delivery failed | channel=%s signal_id=%s error=%s",
                channel["id"],
                signal_id,
                exc,
            )
            if audit:
                self._audit(signal_id, channel["id"], status, message, base, error=str(exc))
            return False

        if audit:
            self._audit(signal_id, channel["id"], "SENT", message, base)
        logger.info(
            "Notification accepted | channel=%s signal_id=%s kind=%s message_type=%s",
            channel["id"],
            signal_id,
            kind,
            message.message_type,
        )
        return True

    def deliver(self, *, signal_id, message, kind="SIGNAL", metadata=None, audit=True):
        # The silence gate reads the signal_events row to decide why a signal must
        # not reach chat. Scan results and periodic summaries (audit=False) have no
        # such row by design, so the gate must not apply to them -- otherwise every
        # scan/summary delivery would be muted and the summary watermark would
        # never advance.
        if audit and self._should_silence(signal_id=signal_id):
            self._audit(
                signal_id,
                "telegram",
                "SILENT",
                message,
                dict(metadata or {}),
                error="suppressed chat noise",
            )
            return False

        sent = False
        for channel in self._targets(kind):
            ok = self._deliver_one(
                channel,
                signal_id=signal_id,
                message=message,
                kind=kind,
                metadata=metadata,
                audit=audit,
            )
            sent = sent or ok
        return sent

    def retry_failed(self, limit=20):
        sent = 0
        current = pd.Timestamp.now(tz=IST_TIMEZONE)
        for row in self.database.failed_deliveries(limit):
            meta = row.get("metadata") or {}
            due = meta.get("next_retry_at")
            if due:
                retry_at = pd.Timestamp(due)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.tz_localize(IST_TIMEZONE)
                if retry_at > current:
                    continue
            text = meta.get("text", "")
            if not text:
                continue
            channel = channel_registry.find(row["channel"])
            if channel is None:
                if channel_registry.load():
                    continue
                channel = self._implicit_telegram()
            message = TelegramMessage(row.get("message_type") or "MSG-RETRY-V1", text)
            if self._deliver_one(
                channel,
                signal_id=row["signal_id"],
                message=message,
                kind=meta.get("kind", "RETRY"),
                metadata={**meta, "retry_of": row["id"]},
            ):
                sent += 1
        return sent

    def _debug_targets(self):
        return {
            "configured": channel_registry.load(),
            "implicit_events": self._implicit_telegram()["events"],
        }

    def set_telegram_send(self, fn):
        """Attach a test harness that owns the Telegram send path."""
        self._telegram_send = fn
