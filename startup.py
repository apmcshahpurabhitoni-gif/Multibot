"""MULTIBOT2 startup announcement."""

from __future__ import annotations

import json
import logging
import os
from urllib import parse, request

from config import (
    APP_VERSION as CONFIG_APP_VERSION,
    LIVE_ASSETS,
    SIGNAL_FRESHNESS_HOURS,
)
from strategies import discover_strategies


APP_NAME = "MULTIBOT2"
APP_VERSION = os.getenv(
    "MULTIBOT2_VERSION",
    CONFIG_APP_VERSION,
)
BUILD = os.getenv(
    "RENDER_GIT_COMMIT",
    "unknown",
)[:8]

# Canonical MULTIBOT2 dashboard.
# Deliberately not configurable so an old Render environment variable
# cannot accidentally point the bot back to another application.
DASHBOARD_URL = (
    "https://multibot2-t74l.onrender.com/dashboard"
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(
    "multibot2.startup"
)

BR = "━━━━━━━━━━━━━━━━━━━━━━"


def telegram_send(
    token: str,
    chat_id: str,
    text: str,
) -> None:
    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
        }
    ).encode()

    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )

    with request.urlopen(
        req,
        timeout=20,
    ) as response:
        data = json.loads(
            response.read()
        )

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram sendMessage failed: {data}"
        )


def _strategy_lines() -> list[str]:
    """Build human-readable startup facts from the canonical strategy registry."""
    try:
        registry = discover_strategies()
        return [
            f"🧩 {strategy.manifest.name}: "
            f"{', '.join(strategy.manifest.timeframes)} · "
            f"{len(strategy.manifest.assets)} assets"
            for strategy in registry.all()
        ]
    except Exception as exc:
        logger.warning("Could not discover strategies for startup announcement: %s", exc)
        return ["🧩 Strategy registry: discovery unavailable"]


def startup_message() -> str:
    lines = [
        f"🤖 {APP_NAME} STARTED",
        BR,
        "🟢 Status: ONLINE",
        f"🏷 Version: {APP_VERSION}",
        f"🔖 Build: {BUILD}",
        "🧪 Mode: PAPER",
        f"🌐 Universe: {len(LIVE_ASSETS)} live assets",
        "🧩 Strategy registry: automatic plug-in discovery",
        *_strategy_lines(),
        f"⏳ Signal freshness: {SIGNAL_FRESHNESS_HOURS}h",
        "💾 Persistence: Supabase + SQLite fallback",
        "",
        "📖 COMMAND GUIDE",
        "/start — Show bot overview",
        "/status — Bot health and runtime status",
        "/signals — Recent signal history",
        "/scan — Run a market scan",
        "/dashboard — Open the live dashboard",
        "/help — Show the command guide",
        "",
        "🌐 DASHBOARD",
        f"👉 {DASHBOARD_URL}",
        BR,
    ]
    return "\n".join(lines)


def whats_new_message() -> str:
    lines = [
        f"🆕 WHAT'S NEW — v{APP_VERSION}",
        BR,
        f"🌐 {len(LIVE_ASSETS)}-asset live universe",
        *_strategy_lines(),
        f"⏳ Freshness: exactly {SIGNAL_FRESHNESS_HOURS} hour",
        "🔁 Duplicate protection survives restart",
        "💾 Supabase authoritative + SQLite fallback",
        "🎨 Dashboard is presentation-only and expandable",
        "",
        "🌐 DASHBOARD",
        f"👉 {DASHBOARD_URL}",
        BR,
    ]
    return "\n".join(lines)

def _send_notice(
    token: str,
    chat_id: str,
    label: str,
    text: str,
) -> None:
    try:
        telegram_send(
            token,
            chat_id,
            text,
        )

        logger.info(
            "%s announcement sent: "
            "version=%s build=%s",
            label,
            APP_VERSION,
            BUILD,
        )

    except Exception as exc:
        logger.warning(
            "%s announcement failed: %s",
            label,
            exc,
        )


def main() -> int:
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )
    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not token or not chat_id:
        logger.warning(
            "Startup Telegram announcement "
            "skipped: Telegram credentials are missing"
        )
        return 0

    _send_notice(
        token,
        chat_id,
        "startup",
        startup_message(),
    )

    _send_notice(
        token,
        chat_id,
        "whats-new",
        whats_new_message(),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
