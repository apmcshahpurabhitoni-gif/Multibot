"""One owner for Telegram delivery, persistence and retry."""
from __future__ import annotations
import logging
from telegram import TelegramConfig, send_message
logger=logging.getLogger("multibot2.notification")

class NotificationService:
    def __init__(self,database,telegram_config=None):
        self.database=database; self.telegram_config=telegram_config
    def _config(self): return self.telegram_config or TelegramConfig.from_env()
    def deliver(self,*,signal_id,message,kind="SIGNAL",metadata=None):
        self.database.record_delivery(signal_id,channel="telegram",status="PENDING",message_type=message.message_type,metadata={**(metadata or {}),"text":message.text,"kind":kind})
        try:
            send_message(message,self._config())
            self.database.record_delivery(signal_id,channel="telegram",status="SENT",message_type=message.message_type,metadata={**(metadata or {}),"text":message.text,"kind":kind})
            return True
        except Exception as exc:
            logger.exception("Telegram delivery failed for %s",signal_id)
            self.database.record_delivery(signal_id,channel="telegram",status="FAILED",error_text=str(exc),message_type=message.message_type,metadata={**(metadata or {}),"text":message.text,"kind":kind})
            return False
    def retry_failed(self,limit=20):
        sent=0
        for row in self.database.failed_deliveries(limit):
            meta=row.get("metadata") or {}; text=meta.get("text","")
            if not text: continue
            from telegram import TelegramMessage
            msg=TelegramMessage(row.get("message_type") or "MSG-RETRY-V1",text)
            if self.deliver(signal_id=row["signal_id"],message=msg,kind=meta.get("kind","RETRY"),metadata={**meta,"retry_of":row["id"]}):
                sent+=1
        return sent
