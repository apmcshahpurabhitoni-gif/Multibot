"""Forex Factory economic calendar with a persistent once-per-day cache."""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from zoneinfo import ZoneInfo

from calendar_store import CalendarStore

IST = ZoneInfo("Asia/Kolkata")
FF_TZ = ZoneInfo("America/New_York")
# Forex Factory publishes the same weekly export through two hostnames.
# The primary host can return 429 for shared cloud IPs, so the CDN hostname
# is an explicit fallback rather than treating one temporary upstream block
# as a calendar outage.
CALENDAR_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
)
NEXT_WEEK_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.json",
)
FOREX_FACTORY_CALENDAR = "https://www.forexfactory.com/calendar"
IMPACTS = ("High", "Medium", "Low", "Holiday")


class CalendarService:
    """Fetch a Forex Factory feed at most once per IST day and reuse it."""

    def __init__(self, path: str | None = None) -> None:
        self.store = CalendarStore(path)
        self._lock = RLock()

    @staticmethod
    def _week_start(day: date) -> date:
        return day - timedelta(days=day.weekday())

    def _feed_url(self, target: date) -> tuple[str, tuple[str, ...]] | None:
        current_week = self._week_start(datetime.now(IST).date())
        target_week = self._week_start(target)
        if target_week == current_week:
            return "thisweek", CALENDAR_URLS
        if target_week == current_week + timedelta(days=7):
            return "nextweek", NEXT_WEEK_URLS
        return None

    @staticmethod
    def _normalise(data: object) -> list[dict]:
        if not isinstance(data, list):
            raise ValueError("Forex Factory calendar feed returned an unexpected payload")
        events: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_date = str(item.get("date") or "").strip()
            if not raw_date:
                continue
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=FF_TZ)
            local_dt = dt.astimezone(IST)
            impact = str(item.get("impact") or "Low").strip().title()
            if impact not in IMPACTS:
                impact = "Low"
            currency = str(item.get("country") or "").strip().upper()
            title = str(item.get("title") or "Economic event").strip()
            events.append({"id": f"{raw_date}|{currency}|{title}", "date": local_dt.date().isoformat(), "time": local_dt.strftime("%H:%M"), "datetime": local_dt.isoformat(), "currency": currency, "impact": impact, "title": title, "actual": str(item.get("actual") or "").strip(), "forecast": str(item.get("forecast") or "").strip(), "previous": str(item.get("previous") or "").strip(), "source": "Forex Factory", "url": FOREX_FACTORY_CALENDAR})
        return sorted(events, key=lambda item: item["datetime"])

    def _load_feed(self, feed_key: str, feed_urls: tuple[str, ...]) -> tuple[list[dict], str, str]:
        cached, fetched_at = self.store.load_for_today(feed_key)
        if cached is not None:
            return cached, fetched_at or "", "CACHED"

        # A failed first attempt is also cached for the day. This prevents UI refreshes
        # and Telegram commands from repeatedly triggering the same Forex Factory 429.
        attempt = self.store.load_attempt_for_today(feed_key)
        if attempt:
            attempted_at, error = attempt
            stale, stale_at = self.store.load_latest(feed_key)
            if stale is not None:
                return stale, stale_at or attempted_at, f"STALE_CACHE: {error}"
            raise RuntimeError(f"Forex Factory feed unavailable today: {error}")

        errors: list[str] = []
        for index, feed_url in enumerate(feed_urls):
            try:
                req = urllib.request.Request(
                    feed_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; Mavis-MULTIBOT2/3.2 economic-calendar)",
                        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                events = self._normalise(json.loads(raw))
                fetched_at = self.store.save_today(feed_key, events)
                source = "FETCHED_TODAY" if index == 0 else "FETCHED_TODAY_FALLBACK"
                return events, fetched_at, source
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")

        error = " | ".join(errors)
        attempted_at = self.store.save_attempt(feed_key, error)
        stale, fetched_at = self.store.load_latest(feed_key)
        if stale is not None:
            return stale, fetched_at or attempted_at, f"STALE_CACHE: {error}"
        raise RuntimeError(f"Forex Factory feed unavailable: {error}")

    def get(self, *, target_date: str | None = None, impacts: set[str] | None = None, force: bool = False) -> dict:
        """Return calendar data. force only refreshes the UI; it never bypasses the daily cache."""
        del force
        target = datetime.now(IST).date() if not target_date else date.fromisoformat(target_date)
        feed = self._feed_url(target)
        if feed is None:
            return {"status": "OUT_OF_RANGE", "source": "Forex Factory", "date": target.isoformat(), "fetched_at": datetime.now(timezone.utc).isoformat(), "items": [], "counts": {impact.lower(): 0 for impact in IMPACTS}, "message": "Forex Factory supplies a rolling current/next week feed; choose a date in that range.", "calendar_url": FOREX_FACTORY_CALENDAR}
        feed_key, feed_urls = feed
        try:
            # The service can be called simultaneously by dashboard polling and
            # refresh actions. Serialize the first fetch so both requests share
            # one upstream download and one persisted cache entry.
            with self._lock:
                events, fetched_at, load_status = self._load_feed(feed_key, feed_urls)
        except Exception as exc:
            return {"status": "OFFLINE", "source": "Forex Factory", "date": target.isoformat(), "fetched_at": datetime.now(timezone.utc).isoformat(), "items": [], "counts": {impact.lower(): 0 for impact in IMPACTS}, "message": str(exc), "calendar_url": FOREX_FACTORY_CALENDAR}
        selected = [event for event in events if event["date"] == target.isoformat()]
        all_counts = {impact.lower(): sum(event["impact"] == impact for event in selected) for impact in IMPACTS}
        selected_impacts = {item.title() for item in (impacts or {"All"})}
        if "All" not in selected_impacts:
            selected = [event for event in selected if event["impact"] in selected_impacts]
        status = "ONLINE" if load_status.startswith("FETCHED_TODAY") else ("CACHED" if load_status == "CACHED" else "STALE_CACHE")
        return {"status": status, "source": "Forex Factory", "date": target.isoformat(), "fetched_at": fetched_at, "items": selected, "counts": all_counts, "message": f"{len(selected)} events for {target.strftime('%d %b %Y')} · {load_status}", "calendar_url": f"{FOREX_FACTORY_CALENDAR}?day={target.strftime('%b').lower()}{target.day}.{target.year}"}

    def refresh(self, *, target_date: str | None = None, impacts: set[str] | None = None) -> dict:
        with self._lock:
            return self.get(target_date=target_date, impacts=impacts)


NewsService = CalendarService
__all__ = ["CalendarService", "NewsService", "IMPACTS"]
