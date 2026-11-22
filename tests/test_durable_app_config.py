import json
import sqlite3
import sys
import types

import bot_settings
import channels
import db as db_module
from db import DatabaseManager


def _fake_libsql_module(remote_path):
    def connect(database, auth_token):
        assert database.startswith("libsql://")
        assert auth_token == "test-token"
        return sqlite3.connect(remote_path, timeout=30)
    return types.SimpleNamespace(connect=connect)


def test_bot_settings_and_notification_channels_survive_turso_restart(tmp_path, monkeypatch):
    remote_path = str(tmp_path / "turso-config.db")
    monkeypatch.setattr(db_module, "TURSO_DATABASE_URL", "libsql://unit-test.aws-ap-south-1.turso.io")
    monkeypatch.setattr(db_module, "TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", str(tmp_path / "unused-default.db"))
    monkeypatch.setitem(sys.modules, "libsql", _fake_libsql_module(remote_path))
    monkeypatch.setattr(bot_settings, "_DATABASE", None)
    monkeypatch.setattr(channels, "_DATABASE", None)

    settings_file = tmp_path / "bot_settings.json"
    legacy_settings = bot_settings.default_settings()
    legacy_settings["session"]["start_hour"] = 8
    settings_file.write_text(json.dumps(legacy_settings), encoding="utf-8")
    monkeypatch.setenv("BOT_SETTINGS_PATH", str(settings_file))

    channels_file = tmp_path / "notification_channels.json"
    legacy_channels = [{
        "id": "alerts",
        "type": "webhook",
        "label": "Alerts",
        "target": "https://example.test/hook",
        "enabled": True,
        "events": ["SIGNAL", "ERROR"],
        "secret": "private-webhook-secret",
    }]
    channels_file.write_text(json.dumps({"channels": legacy_channels}), encoding="utf-8")
    monkeypatch.setenv("NOTIFICATION_CHANNELS_PATH", str(channels_file))

    first = DatabaseManager(str(tmp_path / "ephemeral-a.db"))
    bot_settings.configure_database(first)
    channels.configure_database(first)

    loaded_settings = bot_settings.load()
    loaded_channels = channels.load()
    assert loaded_settings["session"]["start_hour"] == 8
    assert loaded_channels[0]["target"] == "https://example.test/hook"
    assert loaded_channels[0]["secret"] == "private-webhook-secret"

    # The source JSON files are deliberately left untouched by the import.
    assert settings_file.exists()
    assert channels_file.exists()

    # Even if ephemeral files disappear or change, Turso remains authoritative.
    settings_file.unlink()
    channels_file.unlink()
    second = DatabaseManager(str(tmp_path / "ephemeral-b.db"))
    bot_settings.configure_database(second)
    channels.configure_database(second)

    assert bot_settings.load()["session"]["start_hour"] == 8
    persisted_channels = channels.load()
    assert persisted_channels[0]["target"] == "https://example.test/hook"
    assert persisted_channels[0]["secret"] == "private-webhook-secret"

    # Dashboard redaction/round-trip must not erase credentials.
    public = channels.state()["channels"][0]
    assert public["target"] == ""
    assert public["secret"] == ""
    channels.save([{
        "id": "alerts",
        "type": "webhook",
        "label": "Alerts",
        "target": "",
        "enabled": True,
        "events": ["SIGNAL", "ERROR"],
        "secret": "",
    }])
    assert channels.load()[0]["target"] == "https://example.test/hook"
    assert channels.load()[0]["secret"] == "private-webhook-secret"
