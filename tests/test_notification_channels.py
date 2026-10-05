"""Notification channels: the registry, the fan-out and the installable app.

Telegram used to be the only transport, inlined in NotificationService. These
pin both halves of what replaced it: a channel is a validated, persisted value
with a subscription list, and every delivery reaches exactly the channels that
asked for it -- including when one of them is down.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import channels
import notification_service
from telegram import TelegramMessage

ROOT = Path(__file__).resolve().parents[1]


class FakeDatabase:
    """Minimal stand-in for the delivery audit surface."""

    def __init__(self):
        self.rows = []

    def record_delivery(self, signal_id, *, channel, status, attempted_at=None,
                        error_text=None, message_type=None, metadata=None):
        self.rows.append({
            "id": len(self.rows) + 1, "signal_id": signal_id, "channel": channel,
            "status": status, "error": error_text, "message_type": message_type,
            "metadata": dict(metadata or {}),
        })

    def failed_deliveries(self, limit=20):
        latest = {}
        for row in self.rows:
            latest[row["signal_id"]] = row
        return [r for r in latest.values() if r["status"] == "FAILED"][:limit]


@pytest.fixture(autouse=True)
def channel_file(tmp_path, monkeypatch):
    path = tmp_path / "notification_channels.json"
    monkeypatch.setenv("NOTIFICATION_CHANNELS_PATH", str(path))
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    return path


def webhook(channel_id="ops", kind="webhook", events=("SIGNAL",), **overrides):
    channel = {
        "id": channel_id, "type": kind, "label": channel_id.title(),
        "target": "https://example.test/hook", "events": list(events),
    }
    channel.update(overrides)
    return channel


# ---------------------------------------------------------------------------
# Defaults and the canonical shape
# ---------------------------------------------------------------------------

def test_nothing_is_configured_until_something_is_saved(channel_file):
    assert channels.load() == []


def test_the_environment_alone_still_produces_a_telegram_channel(channel_file, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    loaded = channels.load()
    assert [c["type"] for c in loaded] == ["telegram"]
    assert loaded[0]["events"] == list(channels.EVENT_KINDS)


def test_every_requested_event_is_subscribable():
    for event in ("SIGNAL", "TRADE_CLOSED", "SCAN", "ERROR", "STALE", "SUMMARY"):
        assert event in channels.EVENT_KINDS


def test_a_channel_normalizes_and_persists(channel_file):
    channels.save({"channels": [webhook(events=["SIGNAL", "ERROR"])]})
    assert channels.load()[0]["events"] == ["SIGNAL", "ERROR"]
    written = json.loads(channel_file.read_text(encoding="utf-8"))
    assert written["channels"][0]["target"] == "https://example.test/hook"


@pytest.mark.parametrize("payload,expected", [
    ([webhook(kind="sms")], "type must be one of"),
    ([webhook(target="ftp://example.test/hook")], "http(s) URL"),
    ([webhook(kind="telegram", target="https://telegram.test")], "not a URL"),
    ([webhook(events=[])], "at least one event"),
    ([webhook(events=["NOT_AN_EVENT"])], "Unknown notification event"),
    ([webhook(id="Ops")], "Channel ids must be"),
    ([webhook(), webhook()], "listed twice"),
    ([webhook(label="  ")], "a label is required"),
    ([webhook(target="   ")], "a target is required"),
])
def test_bad_channels_are_refused(payload, expected):
    with pytest.raises(ValueError) as caught:
        channels.save({"channels": payload})
    assert expected in str(caught.value)


# ---------------------------------------------------------------------------
# Secrets never reach the browser
# ---------------------------------------------------------------------------

def test_a_read_never_returns_a_webhook_target_or_secret():
    channels.save({"channels": [webhook(kind="slack", target="https://hooks.slack.test/secret", secret="s3cr3t")]})

    view = channels.state()
    channel = view["channels"][0]
    assert channel["target"] == ""
    assert channel["secret"] == ""
    assert channel["has_target"] is True
    assert channel["has_secret"] is True
    dumped = json.dumps(view)
    assert "hooks.slack.test" not in dumped
    assert "s3cr3t" not in dumped


def test_a_telegram_chat_id_is_not_a_secret_and_stays_visible():
    channels.save({"channels": [webhook(kind="telegram", target="-1001234567890")]})
    assert channels.state()["channels"][0]["target"] == "-1001234567890"


def test_a_redacted_round_trip_keeps_the_stored_address():
    """A blank target means "unchanged", not "erase": the form cannot echo it."""
    channels.save({"channels": [webhook(kind="discord", target="https://discord.test/a")]})

    view = channels.state()["channels"]
    view[0]["label"] = "Ops channel"
    channels.save({"channels": view})

    saved = channels.load()[0]
    assert saved["target"] == "https://discord.test/a"
    assert saved["label"] == "Ops channel"


def test_replacing_a_target_does_replace_it():
    channels.save({"channels": [webhook()]})
    channels.save({"channels": [webhook(target="https://example.test/second")]})
    assert channels.load()[0]["target"] == "https://example.test/second"


def test_reset_returns_to_the_environment_default(channel_file, monkeypatch):
    channels.save({"channels": [webhook()]})
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    assert [c["id"] for c in channels.reset()] == ["telegram"]


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------

def _service(db, monkeypatch):
    service = notification_service.NotificationService(db)
    monkeypatch.setattr(service, "_config", lambda: object())
    return service


def test_delivery_reaches_every_subscribed_channel(channel_file, monkeypatch):
    channels.save({"channels": [
        webhook("telegram_channel", kind="telegram", target="-100", events=["SIGNAL"]),
        webhook("ops", events=["SIGNAL"]),
    ]})
    db = FakeDatabase()
    service = _service(db, monkeypatch)
    telegram = []
    monkeypatch.setattr(notification_service, "send_message",
                        lambda message, config: telegram.append(message.text))
    posted = []
    monkeypatch.setattr(channels, "send",
                        lambda channel, message, kind, **kw: posted.append((channel["id"], kind)))

    assert service.deliver(signal_id="sig-1", message=TelegramMessage("MSG-SIGNAL-BUY-V1", "hello")) is True
    assert telegram == ["hello"]
    assert posted == [("ops", "SIGNAL")]
    assert [r["channel"] for r in db.rows if r["status"] == "SENT"] == ["telegram_channel", "ops"]


def test_a_channel_only_receives_the_events_it_subscribed_to(channel_file, monkeypatch):
    channels.save({"channels": [webhook(events=["TRADE_CLOSED"])]})
    db = FakeDatabase()
    service = _service(db, monkeypatch)
    posted = []
    monkeypatch.setattr(channels, "send", lambda channel, message, kind, **kw: posted.append(kind))
    message = TelegramMessage("MSG-SIGNAL-BUY-V1", "hello")

    assert service.deliver(signal_id="sig-1", message=message, kind="SIGNAL") is False
    assert posted == []
    assert service.deliver(signal_id="sig-1", message=message, kind="TRADE_CLOSED") is True
    assert posted == ["TRADE_CLOSED"]


def test_an_unconfigured_deployment_still_delivers_over_telegram(channel_file, monkeypatch):
    db = FakeDatabase()
    service = _service(db, monkeypatch)
    sent = []
    monkeypatch.setattr(notification_service, "send_message",
                        lambda message, config: sent.append(message.text))

    assert service.deliver(signal_id="sig-1", message=TelegramMessage("MSG-TEST-V1", "hi")) is True
    assert sent == ["hi"]
    assert {r["status"] for r in db.rows} == {"PENDING", "SENT"}


def test_one_healthy_channel_is_enough_to_call_the_event_delivered(channel_file, monkeypatch):
    channels.save({"channels": [
        webhook("dead", kind="telegram", target="-100", events=["SIGNAL"]),
        webhook("alive", events=["SIGNAL"]),
    ]})
    db = FakeDatabase()
    service = _service(db, monkeypatch)

    def dead(message, config):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(notification_service, "send_message", dead)
    monkeypatch.setattr(channels, "send", lambda channel, message, kind, **kw: None)

    assert service.deliver(signal_id="sig-1", message=TelegramMessage("MSG-TEST-V1", "hi")) is True
    assert [r["channel"] for r in db.rows if r["status"] == "FAILED"] == ["dead"]


def test_a_failed_channel_is_retried_alone(channel_file, monkeypatch):
    channels.save({"channels": [
        webhook("telegram_channel", kind="telegram", target="-100", events=["SIGNAL"]),
        webhook("ops", events=["SIGNAL"]),
    ]})
    db = FakeDatabase()
    service = _service(db, monkeypatch)
    telegram = []
    monkeypatch.setattr(notification_service, "send_message",
                        lambda message, config: telegram.append(message.text))

    def boom(channel, message, kind, **kw):
        raise RuntimeError("webhook down")

    monkeypatch.setattr(channels, "send", boom)
    assert service.deliver(signal_id="sig-1", message=TelegramMessage("MSG-TEST-V1", "hi")) is True
    assert [r["channel"] for r in db.rows if r["status"] == "FAILED"] == ["ops"]

    # The two-minute backoff is what the real worker waits for; this test is
    # about the retry target, so it makes the row due immediately.
    for row in db.rows:
        if row["status"] == "FAILED":
            row["metadata"]["next_retry_at"] = "2000-01-01T00:00:00+05:30"
    monkeypatch.setattr(channels, "send",
                        lambda channel, message, kind, **kw: telegram.append("retry:" + channel["id"]))
    assert service.retry_failed() == 1
    # The channel that already accepted the message is never sent a second copy.
    assert telegram == ["hi", "retry:ops"]


def test_events_with_no_signal_row_are_sent_without_a_delivery_row(channel_file, monkeypatch):
    """`signal_deliveries.signal_id` is a foreign key, so scan output is unaudited."""
    channels.save({"channels": [webhook(events=["SCAN"])]})
    db = FakeDatabase()
    service = _service(db, monkeypatch)
    posted = []
    monkeypatch.setattr(channels, "send", lambda channel, message, kind, **kw: posted.append(kind))

    assert service.deliver(signal_id="scan:run-1", message=TelegramMessage("MSG-SCAN-COMPLETE-V1", "done"),
                           kind="SCAN", audit=False) is True
    assert posted == ["SCAN"]
    assert db.rows == []


# ---------------------------------------------------------------------------
# Periodic summaries
# ---------------------------------------------------------------------------

def test_due_summaries_fires_once_a_day_and_once_a_week(monkeypatch, tmp_path):
    import main

    monkeypatch.setenv("SUMMARY_STATE_PATH", str(tmp_path / "summary.json"))
    base = pd.Timestamp("2026-10-05 19:00", tz="Asia/Kolkata")
    weekly_day = base.weekday()

    assert main.due_summaries(base.replace(hour=9), {}, daily_hour=18, weekly_day=weekly_day) == []
    assert main.due_summaries(base, {}, daily_hour=18, weekly_day=weekly_day) == ["daily", "weekly"]
    assert main.due_summaries(base.replace(hour=20), {"daily": "2026-10-05", "weekly": "2026-10-05"},
                              daily_hour=18, weekly_day=weekly_day) == []

    tomorrow = base + pd.Timedelta(days=1)
    if tomorrow.weekday() == weekly_day:
        tomorrow += pd.Timedelta(days=1)
    assert main.due_summaries(tomorrow, {"daily": "2026-10-05"}, daily_hour=18,
                              weekly_day=weekly_day) == ["daily"]


def test_summaries_follow_the_live_subscriptions(channel_file, monkeypatch, tmp_path):
    """A channel added this afternoon gets today's summary, not next restart's.

    The scheduler used to start only when a channel existed at boot, so adding
    one from the Tools screen silently meant no summaries until the process was
    restarted. It now reads the subscriptions every tick.
    """
    import types

    import main

    monkeypatch.setenv("SUMMARY_STATE_PATH", str(tmp_path / "summary.json"))
    # Hour 0 is always due, so "is it the right time" never depends on the run.
    monkeypatch.setenv("SUMMARY_DAILY_HOUR", "0")
    # Tomorrow's weekday means the weekly summary is never also due.
    monkeypatch.setenv("SUMMARY_WEEKLY_DAY",
                       str((pd.Timestamp.now(tz="Asia/Kolkata").weekday() + 1) % 7))
    monkeypatch.setattr(main, "DB", types.SimpleNamespace(load_trades=lambda *a, **k: []))

    class Notifier:
        def __init__(self):
            self.calls = []

        def deliver(self, **kwargs):
            self.calls.append(kwargs)
            return True

    notifier = Notifier()
    monkeypatch.setattr(main, "SERVICE", types.SimpleNamespace(notifier=notifier))

    # Nobody subscribes: no message, and no watermark to spend.
    assert main.run_summaries() == []
    assert notifier.calls == []

    channels.save({"channels": [webhook(events=["SUMMARY"])]})
    assert main.run_summaries() == ["daily"]
    assert [call["kind"] for call in notifier.calls] == ["SUMMARY"]

    # And the next tick does not send the same day's summary again.
    assert main.run_summaries() == []
    assert len(notifier.calls) == 1


# ---------------------------------------------------------------------------
# The installable app, and the Tools card
# ---------------------------------------------------------------------------

def test_the_dashboard_installs_as_an_app():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in html
    assert 'href="/manifest.webmanifest"' in html
    assert 'src="notifications.js"' in html
    assert "serviceWorker" in html

    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/dashboard"
    assert manifest["icons"], "an installable app needs at least one icon"
    for icon in manifest["icons"]:
        assert (ROOT / icon["src"].lstrip("/")).is_file()
    assert (ROOT / "sw.js").is_file()


def test_the_server_serves_the_app_and_the_channel_api():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    for asset in ("/manifest.webmanifest", "/sw.js", "/app-icon.svg", "/notifications.js", "/api/notifications"):
        assert asset in source, f"main.py does not serve {asset}"


def test_the_notifications_card_does_not_borrow_the_trading_save_hook():
    """app.js writes accounts/assets/routing as one document; a channel is not."""
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    start = html.index('data-tool-key="notifications"')
    card = html[start:html.index("</section>", start)]

    assert "data-notifications-save" in card
    assert "data-notifications-reset" in card
    assert "data-save-settings" not in card
    assert "data-settings-status" not in card
    assert "notificationChannels" in card
