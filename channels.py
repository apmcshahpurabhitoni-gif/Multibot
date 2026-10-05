"""Operator-editable notification channels.

Telegram was the only transport, hard-wired into `NotificationService`. This
module makes the transport a value: a small registry of channels, each with an
id, a type, a target and the events it subscribes to. Every channel receives the
same rendered message the Telegram builders already produce, so adding Discord,
Slack or a generic webhook never touches a strategy, the trade monitor or the
scan loop -- they all still call `NotificationService.deliver()` and fan-out
happens here.

Targets are secrets: a Discord/Slack webhook URL *is* the credential. The
dashboard is unauthenticated, so `state()` never returns a webhook target or an
auth secret -- it returns whether one is stored, and a replacement is only ever
written from the Tools screen. `POST` with an empty target keeps the stored one.
"""
from __future__ import annotations

import json
import logging
import os
import re
from urllib import error, request

from telegram import TelegramMessage

logger = logging.getLogger("multibot2.channels")

#: The events an operator can subscribe a channel to. The first three already
#: fire from the existing delivery call sites; the rest are wired in main.py.
EVENT_KINDS: tuple[str, ...] = ("SIGNAL", "TRADE_CLOSED", "REMINDER", "STALE", "SCAN", "ERROR", "SUMMARY")

#: Transports that need nothing but the standard library. `telegram` is sent by
#: NotificationService (it owns the bot token); the others are plain JSON POSTs.
CHANNEL_TYPES: tuple[str, ...] = ("telegram", "discord", "slack", "webhook")

_WEBHOOK_TYPES = frozenset({"discord", "slack", "webhook"})

CHANNEL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

DEFAULT_CHANNELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notification_channels.json")


def channels_path() -> str:
    return os.getenv("NOTIFICATION_CHANNELS_PATH") or DEFAULT_CHANNELS_PATH


# ---------------------------------------------------------------------------
# Canonical shape
# ---------------------------------------------------------------------------

def default_channels() -> list[dict]:
    """The shipped default: Telegram, if the environment configures it.

    Read from the environment rather than persisted, so a checkout that already
    had a working Telegram token keeps delivering without anyone visiting Tools.
    """
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return []
    return [{
        "id": "telegram",
        "type": "telegram",
        "label": "Telegram",
        "target": chat_id,
        "enabled": True,
        "events": list(EVENT_KINDS),
        "secret": "",
    }]


def _clean_id(value, taken: set[str]) -> str:
    if not isinstance(value, str) or not CHANNEL_ID_PATTERN.match(value):
        raise ValueError("Channel ids must be lower case letters, digits, dashes or underscores (2-32 characters)")
    if value in taken:
        raise ValueError(f"Channel {value} is listed twice")
    return value


def _clean_events(value) -> list[str]:
    if value is None:
        return list(EVENT_KINDS)
    if not isinstance(value, list) or not value:
        raise ValueError("A channel must subscribe to at least one event")
    out: list[str] = []
    for item in value:
        if item not in EVENT_KINDS:
            raise ValueError(f"Unknown notification event: {item}")
        if item not in out:
            out.append(item)
    return out


def normalize(payload) -> list[dict]:
    """Validate an incoming document and return it in canonical shape."""
    raw = payload.get("channels") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise ValueError("Channels must be a list")
    out: list[dict] = []
    taken: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Channel {index + 1} must be an object")
        cid = _clean_id(item.get("id"), taken)
        taken.add(cid)
        kind = item.get("type")
        if kind not in CHANNEL_TYPES:
            raise ValueError(f"Channel {cid}: type must be one of {', '.join(CHANNEL_TYPES)}")
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Channel {cid}: a label is required")
        target = item.get("target")
        if target is not None and not isinstance(target, str):
            raise ValueError(f"Channel {cid}: target must be text")
        target = (target or "").strip()
        if not target:
            raise ValueError(f"Channel {cid}: a target is required")
        if kind in _WEBHOOK_TYPES and not target.startswith(("http://", "https://")):
            raise ValueError(f"Channel {cid}: a webhook target must be an http(s) URL")
        if kind == "telegram" and target.startswith(("http://", "https://")):
            raise ValueError(f"Channel {cid}: a Telegram target is a chat id, not a URL")
        secret = item.get("secret") or ""
        if not isinstance(secret, str):
            raise ValueError(f"Channel {cid}: secret must be text")
        out.append({
            "id": cid,
            "type": kind,
            "label": label.strip(),
            "target": target,
            "enabled": bool(item.get("enabled", True)),
            "events": _clean_events(item.get("events")),
            "secret": secret.strip(),
        })
    return out


def _merge_stored(incoming, stored: list[dict]) -> list:
    """Keep a stored target/secret when the dashboard sends a redacted blank.

    The read path strips secrets, so the round-trip sends them back empty. A
    blank means "unchanged", not "erase" -- the only way to remove an address is
    to delete the channel, and the only way to change one is to type a new one.
    Runs before validation because the redacted document would otherwise fail
    the "a target is required" check.
    """
    if not isinstance(incoming, list):
        return incoming
    by_id = {c["id"]: c for c in stored}
    out = []
    for item in incoming:
        if isinstance(item, dict):
            item = dict(item)
            previous = by_id.get(item.get("id"))
            if previous and previous.get("type") == item.get("type"):
                if not str(item.get("target") or "").strip():
                    item["target"] = previous.get("target", "")
                if not str(item.get("secret") or "").strip():
                    item["secret"] = previous.get("secret", "")
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def load() -> list[dict]:
    """Return the saved channels, falling back to the environment default."""
    path = channels_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return normalize(raw)
    except FileNotFoundError:
        return default_channels()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Notification channels unreadable; using defaults | path=%s error=%s", path, exc)
        return default_channels()


def save(payload) -> list[dict]:
    """Validate, persist and return the channel list.

    The incoming document is merged over what is on disk first, because the
    dashboard can only echo back a redacted target for webhook channels.
    """
    raw = payload.get("channels") if isinstance(payload, dict) else payload
    channels = normalize(_merge_stored(raw, load()))
    path = channels_path()
    try:
        _write(path, {"channels": channels})
    except OSError as exc:
        raise ValueError(f"Could not write {path}: {exc}") from exc
    logger.info("Notification channels updated | channels=%d enabled=%d",
                len(channels), sum(c["enabled"] for c in channels))
    return channels


def reset() -> list[dict]:
    try:
        os.remove(channels_path())
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ValueError(f"Could not remove {channels_path()}: {exc}") from exc
    return load()


def state() -> dict:
    """The live channels for the dashboard, with every secret redacted."""
    channels = []
    for channel in load():
        public = dict(channel)
        public["has_secret"] = bool(channel["secret"])
        public["secret"] = ""
        if channel["type"] in _WEBHOOK_TYPES:
            public["has_target"] = bool(channel["target"])
            public["target"] = ""
        channels.append(public)
    return {
        "channels": channels,
        "options": {
            "types": list(CHANNEL_TYPES),
            "events": list(EVENT_KINDS),
            "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        },
    }


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def find(channel_id: str) -> dict | None:
    for channel in load():
        if channel["id"] == channel_id:
            return channel
    return None


def payload_for(channel: dict, message: TelegramMessage, kind: str) -> dict:
    """The JSON body for a webhook-style transport.

    Slack and Discord both ignore unknown keys, and a generic receiver gets the
    structured event alongside the rendered text, so one body serves all three.
    """
    body = {
        "title": f"MULTIBOT2 · {kind}",
        "event": kind,
        "message_type": message.message_type,
        "text": message.text,
    }
    if channel["type"] == "discord":
        return {"content": message.text}
    if channel["type"] == "slack":
        return {"text": message.text}
    return body


def send(channel: dict, message: TelegramMessage, kind: str, *, timeout: int = 15) -> None:
    """POST one message to a webhook-style channel. Raises on failure."""
    if not message.text.strip():
        raise ValueError("Cannot send an empty notification")
    if channel["type"] == "telegram":
        raise ValueError("Telegram channels are delivered by NotificationService")
    data = json.dumps(payload_for(channel, message, kind)).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if channel["secret"]:
        headers["Authorization"] = f"Bearer {channel['secret']}"
    req = request.Request(channel["target"], data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"{channel['type']} webhook failed: HTTP {response.status}")
    except error.HTTPError as exc:
        raise RuntimeError(f"{channel['type']} webhook failed: HTTP {exc.code} {exc.reason}") from exc


__all__ = [
    "EVENT_KINDS", "CHANNEL_TYPES", "default_channels", "normalize", "load",
    "save", "reset", "state", "find", "send", "payload_for",
]
