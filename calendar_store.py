"""Durable weekly cache for the economic calendar.

The dashboard never needs to contact Forex Factory after a week has been cached.
Local SQLite is a fast runtime cache; when Supabase is configured the same payload
is mirrored through the existing durable market_data_cache table so Render restarts
do not erase the calendar.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import DatabaseManager

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_PATH = os.getenv("BOT_STATE_DB_PATH", "/tmp/workspace/multibot2_state.db")


class CalendarStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or DEFAULT_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.database = DatabaseManager(self.path)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS forex_calendar_week_cache (
                    feed_key TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    events TEXT NOT NULL,
                    PRIMARY KEY(feed_key, week_start)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS forex_calendar_attempts (
                    feed_key TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    error TEXT NOT NULL,
                    PRIMARY KEY(feed_key, week_start)
                )"""
            )
            conn.commit()

    @staticmethod
    def cache_key(feed_key: str, week_start: str) -> str:
        return f"calendar|{feed_key}|{week_start}"

    def load_week(self, feed_key: str, week_start: str) -> tuple[list[dict] | None, str | None]:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT events, fetched_at FROM forex_calendar_week_cache WHERE feed_key=? AND week_start=?",
                (feed_key, week_start),
            ).fetchone()
        if row:
            try:
                events = json.loads(row[0])
                if isinstance(events, list):
                    return events, row[1]
            except (TypeError, ValueError):
                pass

        remote = self.database.load_market_data_cache(self.cache_key(feed_key, week_start))
        if not remote:
            return None, None
        try:
            payload = json.loads(remote["payload"]) if isinstance(remote.get("payload"), str) else remote.get("payload") or {}
            events = payload.get("events")
            fetched_at = payload.get("fetched_at") or remote.get("updated_at")
            if not isinstance(events, list):
                return None, None
        except (TypeError, ValueError, AttributeError):
            return None, None

        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO forex_calendar_week_cache(feed_key,week_start,fetched_at,events) VALUES(?,?,?,?)",
                (feed_key, week_start, str(fetched_at), json.dumps(events, default=str)),
            )
            conn.commit()
        return events, str(fetched_at)

    def save_week(self, feed_key: str, week_start: str, events: list[dict]) -> str:
        fetched_at = datetime.now(IST).isoformat()
        encoded = json.dumps(events, default=str, separators=(",", ":"))
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO forex_calendar_week_cache(feed_key,week_start,fetched_at,events) VALUES(?,?,?,?)",
                (feed_key, week_start, fetched_at, encoded),
            )
            conn.execute(
                "DELETE FROM forex_calendar_attempts WHERE feed_key=? AND week_start=?",
                (feed_key, week_start),
            )
            conn.commit()

        # Reuse the production cache table already known to Supabase. Calendar
        # persistence is best-effort: a remote outage must not make the UI fail.
        self.database.save_market_data_cache(
            self.cache_key(feed_key, week_start),
            "FOREX_FACTORY",
            "1w",
            feed_key,
            False,
            json.dumps({"week_start": week_start, "fetched_at": fetched_at, "events": events}, default=str),
            fetched_at,
        )
        return fetched_at

    def load_latest(self) -> tuple[list[dict] | None, str | None]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT events, fetched_at FROM forex_calendar_week_cache ORDER BY fetched_at DESC"
            ).fetchall()
        merged: list[dict] = []
        latest = None
        seen = set()
        for events_raw, fetched_at in rows:
            try:
                events = json.loads(events_raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(events, list):
                continue
            latest = latest or fetched_at
            for event in events:
                key = event.get("id") or json.dumps(event, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    merged.append(event)
        return (merged or None), latest

    def load_attempt_recent(self, feed_key: str, week_start: str, minutes: int = 30) -> tuple[str, str] | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT attempted_at, error FROM forex_calendar_attempts WHERE feed_key=? AND week_start=?",
                (feed_key, week_start),
            ).fetchone()
        if not row:
            return None
        try:
            attempted = datetime.fromisoformat(row[0])
            if datetime.now(IST) - attempted.astimezone(IST) <= timedelta(minutes=minutes):
                return row[0], row[1]
        except ValueError:
            pass
        return None

    def save_attempt(self, feed_key: str, week_start: str, error: str) -> str:
        attempted_at = datetime.now(IST).isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO forex_calendar_attempts(feed_key,week_start,attempted_at,error) VALUES(?,?,?,?)",
                (feed_key, week_start, attempted_at, error),
            )
            conn.commit()
        return attempted_at
