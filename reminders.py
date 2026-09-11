"""Persistent reminder worker using the shared notification owner."""
from __future__ import annotations
import json,threading
import pandas as pd
from config import IST_TIMEZONE
from db import DatabaseManager
from notification_service import NotificationService
from telegram import reminder_message

class ReminderService:
    def __init__(self,database=None,telegram_config=None,notifier=None):
        self.database=database or DatabaseManager(); self.notifier=notifier or NotificationService(self.database,telegram_config); self._stop=threading.Event()
    def run_once(self,now=None):
        current=pd.Timestamp.now(tz=IST_TIMEZONE) if now is None else pd.Timestamp(now)
        if current.tzinfo is None: raise ValueError("Reminder time must be timezone-aware")
        current=current.tz_convert(IST_TIMEZONE); sent=0
        for row in self.database.due_reminders(current.isoformat()):
            text=row.get("message_text") or ""
            if not text: continue
            try: meta=json.loads(row.get("metadata") or "{}")
            except Exception: meta={}
            sid=str(meta.get("signal_id") or row["signal_key"])
            if self.notifier.deliver(signal_id=sid,message=reminder_message(text),kind="REMINDER",metadata={"signal_key":row["signal_key"]}):
                self.database.mark_reminder_sent(row["signal_key"],current.isoformat()); sent+=1
        return sent
    def start(self,interval_seconds=30):
        def loop():
            while not self._stop.is_set():
                try:self.run_once()
                finally:self._stop.wait(interval_seconds)
        t=threading.Thread(target=loop,daemon=True,name="multibot2-reminders"); t.start(); return t
    def stop(self): self._stop.set()
__all__=["ReminderService"]
