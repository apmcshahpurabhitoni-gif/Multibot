"""One owner for Telegram delivery, persistence and bounded retry."""
from __future__ import annotations
import logging
import pandas as pd
from config import IST_TIMEZONE
from telegram import TelegramConfig, TelegramMessage, send_message

logger = logging.getLogger("multibot2.notification")

class NotificationService:
    MAX_RETRIES = 3

    def __init__(self, database, telegram_config=None):
        self.database = database
        self.telegram_config = telegram_config

    def _config(self):
        return self.telegram_config or TelegramConfig.from_env()

    def deliver(self, *, signal_id, message, kind="SIGNAL", metadata=None):
        base = dict(metadata or {})
        base.update({"text": message.text, "kind": kind})
        self.database.record_delivery(
            signal_id, channel="telegram", status="PENDING",
            message_type=message.message_type, metadata=base
        )
        try:
            send_message(message, self._config())
            self.database.record_delivery(
                signal_id, channel="telegram", status="SENT",
                message_type=message.message_type, metadata=base
            )
            return True
        except Exception as exc:
            retry_count = int(base.get("retry_count", 0)) + 1
            status = "PERMANENT_FAILURE" if retry_count >= self.MAX_RETRIES else "FAILED"
            base["retry_count"] = retry_count
            if status == "FAILED":
                base["next_retry_at"] = (
                    pd.Timestamp.now(tz=IST_TIMEZONE) +
                    pd.Timedelta(minutes=2 ** retry_count)
                ).isoformat()
            logger.exception("Telegram delivery failed for %s", signal_id)
            self.database.record_delivery(
                signal_id, channel="telegram", status=status,
                error_text=str(exc), message_type=message.message_type,
                metadata=base
            )
            return False

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
            msg = TelegramMessage(
                row.get("message_type") or "MSG-RETRY-V1", text
            )
            if self.deliver(
                signal_id=row["signal_id"], message=msg,
                kind=meta.get("kind", "RETRY"),
                metadata={**meta, "retry_of": row["id"]}
            ):
                sent += 1
        return sent
