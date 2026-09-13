"""Cache-first Forex Factory economic calendar.

One successful download is retained for the entire week. The service first reads
durable cache, then fetches at most once per missing week. JSON export is primary;
the normal calendar page is a low-frequency fallback when the export endpoint
rate-limits shared cloud IPs.
"""
from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from calendar_store import CalendarStore

IST = ZoneInfo("Asia/Kolkata")
FF_TZ = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")
FOREX_FACTORY_CALENDAR = "https://www.forexfactory.com/calendar"
JSON_URLS = {
    "thisweek": (
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
    ),
    "nextweek": (
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
        "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.json",
    ),
}
XML_URLS = {
    key: tuple(url.rsplit(".", 1)[0] + ".xml" for url in urls)
    for key, urls in JSON_URLS.items()
}
IMPACTS = ("High", "Medium", "Low", "Holiday")


class CalendarService:
    """Return all cached events grouped by date; never poll upstream from the UI."""

    def __init__(self, path: str | None = None) -> None:
        self.store = CalendarStore(path)
        self._lock = RLock()

    @staticmethod
    def _week_start(day: date) -> date:
        return day - timedelta(days=day.weekday())

    @staticmethod
    def _week_key(day: date) -> str:
        current = CalendarService._week_start(datetime.now(IST).date())
        target = CalendarService._week_start(day)
        return "thisweek" if target == current else "nextweek"

    @staticmethod
    def _impact(value: object, title: str = "") -> str:
        text = f"{value or ''} {title}".lower()
        if "holiday" in text or "bank holiday" in title.lower():
            return "Holiday"
        if "high" in text or "red" in text:
            return "High"
        if "medium" in text or "med" in text or "orange" in text:
            return "Medium"
        return "Low"

    @classmethod
    def _normalise_json(cls, data: object) -> list[dict]:
        if not isinstance(data, list):
            raise ValueError("Forex Factory JSON returned an unexpected payload")
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
            title = str(item.get("title") or "Economic event").strip()
            currency = str(item.get("country") or item.get("currency") or "ALL").strip().upper()
            impact = cls._impact(item.get("impact"), title)
            events.append({
                "id": f"{raw_date}|{currency}|{title}",
                "date": local_dt.date().isoformat(),
                "time": local_dt.strftime("%H:%M"),
                "datetime": local_dt.isoformat(),
                "currency": currency,
                "impact": impact,
                "title": title,
                "actual": str(item.get("actual") or "").strip(),
                "forecast": str(item.get("forecast") or "").strip(),
                "previous": str(item.get("previous") or "").strip(),
                "source": "Forex Factory",
                "url": FOREX_FACTORY_CALENDAR,
            })
        return cls._dedupe(events)

    @classmethod
    def _normalise_xml(cls, raw: str) -> list[dict]:
        root = ET.fromstring(raw)
        events: list[dict] = []
        for node in root.findall(".//event"):
            def value(name: str) -> str:
                child = node.find(name)
                return (child.text or "").strip() if child is not None else ""

            title = value("title") or "Economic event"
            currency = value("country").upper() or "ALL"
            raw_date, raw_time = value("date"), value("time")
            parsed_date = None
            for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    pass
            if parsed_date is None:
                continue
            if raw_time.lower() in {"", "all day", "tentative"} or "day" in raw_time.lower():
                hour, minute = 0, 0
                display_time = "All day"
            else:
                parsed_time = None
                for fmt in ("%I:%M%p", "%I:%M %p", "%H:%M"):
                    try:
                        parsed_time = datetime.strptime(raw_time.upper(), fmt)
                        break
                    except ValueError:
                        pass
                if parsed_time is None:
                    hour, minute, display_time = 0, 0, "All day"
                else:
                    hour, minute = parsed_time.hour, parsed_time.minute
                    display_time = f"{hour:02d}:{minute:02d}"
            local_dt = datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, tzinfo=timezone.utc).astimezone(IST)
            events.append({
                "id": f"{raw_date}|{raw_time}|{currency}|{title}",
                "date": local_dt.date().isoformat(),
                "time": display_time if display_time == "All day" else local_dt.strftime("%H:%M"),
                "datetime": local_dt.isoformat(),
                "currency": currency,
                "impact": cls._impact(value("impact"), title),
                "title": title,
                "actual": value("actual"),
                "forecast": value("forecast"),
                "previous": value("previous"),
                "source": "Forex Factory",
                "url": FOREX_FACTORY_CALENDAR,
            })
        if not events:
            raise ValueError("XML feed returned zero events")
        return cls._dedupe(events)

    @classmethod
    def _normalise_html(cls, html: str, week_start: date) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("tr.calendar__row, tr.calendar_row")
        if not rows:
            raise ValueError("Forex Factory calendar page contained no event rows")

        events: list[dict] = []
        current_date: date | None = None
        current_time = "00:00"

        def cell(row, selector: str) -> str:
            node = row.select_one(selector)
            return node.get_text(" ", strip=True) if node else ""

        for row in rows:
            date_text = cell(row, "td.calendar__date")
            if date_text:
                cleaned = re.sub(r"\s+", " ", date_text)
                parsed = None
                for fmt in ("%a %b %d", "%a %b %-d"):
                    try:
                        parsed = datetime.strptime(cleaned, fmt).date().replace(year=week_start.year)
                        break
                    except (ValueError, TypeError):
                        pass
                if parsed is None:
                    match = re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})", cleaned)
                    if match:
                        parsed = datetime.strptime(f"{match.group(2)} {match.group(3)} {week_start.year}", "%b %d %Y").date()
                if parsed:
                    # Week feeds around New Year can cross into the next year.
                    if parsed < week_start - timedelta(days=7):
                        parsed = parsed.replace(year=parsed.year + 1)
                    current_date = parsed

            time_text = cell(row, "td.calendar__time")
            if time_text:
                current_time = time_text
            currency = cell(row, "td.calendar__currency").upper() or "ALL"
            title = cell(row, "td.calendar__event-title, td.calendar__event")
            if not title:
                continue
            impact_node = row.select_one("td.calendar__impact span, td.calendar__impact")
            impact_raw = " ".join(impact_node.get("class", [])) + " " + (impact_node.get("title", "") if impact_node else "") if impact_node else ""
            impact = cls._impact(impact_raw, title)
            actual = cell(row, "td.calendar__actual")
            forecast = cell(row, "td.calendar__forecast")
            previous = cell(row, "td.calendar__previous")
            event_date = current_date or week_start

            raw_time = current_time.strip().lower()
            if raw_time in {"all day", "tentative", ""} or "day" in raw_time:
                hour, minute = 0, 0
            else:
                match = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m)?", raw_time)
                if not match:
                    hour, minute = 0, 0
                else:
                    hour, minute = int(match.group(1)), int(match.group(2))
                    meridiem = match.group(3)
                    if meridiem == "pm" and hour != 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0
            dt = datetime(event_date.year, event_date.month, event_date.day, hour, minute, tzinfo=LONDON).astimezone(IST)
            events.append({
                "id": f"{event_date.isoformat()}|{current_time}|{currency}|{title}",
                "date": dt.date().isoformat(),
                "time": "All day" if raw_time in {"all day", "tentative", ""} or "day" in raw_time else dt.strftime("%H:%M"),
                "datetime": dt.isoformat(),
                "currency": currency,
                "impact": impact,
                "title": title,
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "source": "Forex Factory",
                "url": FOREX_FACTORY_CALENDAR,
            })
        return cls._dedupe(events)

    @staticmethod
    def _dedupe(events: list[dict]) -> list[dict]:
        seen = set()
        output = []
        for event in events:
            key = event.get("id")
            if key in seen:
                continue
            seen.add(key)
            output.append(event)
        return sorted(output, key=lambda item: (item.get("date", ""), item.get("datetime", ""), item.get("title", "")))

    @staticmethod
    def _request(url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Mavis-MULTIBOT2/3.3; economic-calendar cache)",
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")

    def _fetch_week(self, feed_key: str, week_start: date) -> tuple[list[dict], str]:
        errors: list[str] = []
        for url in JSON_URLS[feed_key]:
            try:
                events = self._normalise_json(json.loads(self._request(url)))
                if events:
                    return events, "JSON"
                raise ValueError("JSON feed returned zero events")
            except Exception as exc:
                errors.append(f"json:{type(exc).__name__}: {exc}")

        # XML is an independent export format and is a second structured
        # fallback before HTML parsing.
        for url in XML_URLS[feed_key]:
            try:
                events = self._normalise_xml(self._request(url))
                if events:
                    return events, "XML_FALLBACK"
            except Exception as exc:
                errors.append(f"xml:{type(exc).__name__}: {exc}")

        # Export endpoints have a documented per-IP limit. The ordinary calendar
        # page is intentionally only used once for a missing week, never per UI load.
        try:
            suffix = "next" if feed_key == "nextweek" else "this"
            html = self._request(f"{FOREX_FACTORY_CALENDAR}?week={suffix}")
            events = self._normalise_html(html, week_start)
            if events:
                return events, "HTML_FALLBACK"
            raise ValueError("calendar page returned zero events")
        except Exception as exc:
            errors.append(f"html:{type(exc).__name__}: {exc}")
        raise RuntimeError(" | ".join(errors))

    def _load_week(self, feed_key: str, week_start: date) -> tuple[list[dict], str, str]:
        week = week_start.isoformat()
        cached, fetched_at = self.store.load_week(feed_key, week)
        if cached is not None:
            return cached, fetched_at or "", "CACHED"

        recent = self.store.load_attempt_recent(feed_key, week, minutes=30)
        if recent:
            raise RuntimeError(f"Calendar fetch cooling down after failure: {recent[1]}")

        try:
            events, source = self._fetch_week(feed_key, week_start)
            fetched_at = self.store.save_week(feed_key, week, events)
            return events, fetched_at, f"FETCHED_{source}"
        except Exception as exc:
            self.store.save_attempt(feed_key, week, str(exc))
            raise

    @staticmethod
    def _counts(items: list[dict]) -> dict:
        return {impact.lower(): sum(item.get("impact") == impact for item in items) for impact in IMPACTS}

    def _days_payload(self, items: list[dict], impacts: set[str]) -> list[dict]:
        allowed = {item.title() for item in impacts} if impacts else {"All"}
        grouped: dict[str, list[dict]] = {}
        for item in items:
            if "All" not in allowed and item.get("impact") not in allowed:
                continue
            grouped.setdefault(item["date"], []).append(item)
        return [
            {
                "date": day,
                "label": datetime.fromisoformat(day).strftime("%A · %d %B"),
                "items": sorted(rows, key=lambda row: (row.get("datetime", ""), row.get("title", ""))),
                "counts": self._counts(rows),
            }
            for day, rows in sorted(grouped.items())
        ]

    def get(self, *, target_date: str | None = None, impacts: set[str] | None = None, force: bool = False) -> dict:
        # force deliberately does not bypass cache. Refresh means "re-read saved
        # data", not "make another upstream request".
        del force
        today = datetime.now(IST).date()
        current_week = self._week_start(today)
        next_week = current_week + timedelta(days=7)
        statuses = []
        all_events: list[dict] = []
        fetched_values = []
        with self._lock:
            for key, week in (("thisweek", current_week), ("nextweek", next_week)):
                try:
                    events, fetched_at, status = self._load_week(key, week)
                    all_events.extend(events)
                    statuses.append(status)
                    if fetched_at:
                        fetched_values.append(fetched_at)
                except Exception as exc:
                    statuses.append(f"FAILED:{type(exc).__name__}")
                    # A valid week from cache must still render even if the other
                    # week's upstream source is temporarily unavailable.
                    continue

        all_events = self._dedupe(all_events)
        if target_date:
            target = date.fromisoformat(target_date)
            selected = [item for item in all_events if item.get("date") == target.isoformat()]
        else:
            # Dashboard calendar is an upcoming agenda: today, tomorrow, then the
            # following dates. Every impact is retained.
            selected = [item for item in all_events if item.get("date", "") >= today.isoformat()]

        all_counts = self._counts(selected)
        days = self._days_payload(selected, impacts or {"All"})
        flat_items = [item for day in days for item in day["items"]]
        if flat_items:
            source_status = "CACHED" if all(status == "CACHED" for status in statuses if not status.startswith("FAILED")) else "ONLINE"
            message = f"{len(flat_items)} events across {len(days)} date{'s' if len(days) != 1 else ''}. Saved feeds are reused until the next week."
        else:
            source_status = "OFFLINE" if not all_events else "CACHED"
            message = "No saved upcoming calendar events are available yet." if not all_events else "No events match the selected date."

        return {
            "status": source_status,
            "source": "Forex Factory",
            "date": target_date or today.isoformat(),
            "fetched_at": max(fetched_values) if fetched_values else None,
            "items": flat_items,
            "days": days,
            "counts": all_counts,
            "message": message,
            "calendar_url": FOREX_FACTORY_CALENDAR,
            "cache_policy": "WEEKLY",
        }

    def refresh(self, *, target_date: str | None = None, impacts: set[str] | None = None) -> dict:
        return self.get(target_date=target_date, impacts=impacts)


NewsService = CalendarService
__all__ = ["CalendarService", "NewsService", "IMPACTS"]
