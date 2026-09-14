"""Canonical release metadata and What's New source for MULTIBOT2."""
from __future__ import annotations
from typing import Final

APP_VERSION: Final[str] = "3.2.5"

RELEASE_HIGHLIGHTS: Final[tuple[str, ...]] = (
    "🎨 Shared ponytail UI system now keeps Home, Signals, History, Calendar and Tools visually consistent.",
    "📈 Home and Backtest use real equity curves for account and strategy performance instead of misleading bar summaries.",
    "🧪 Backtest results are separated into overview, equity curve, performance, completed trades and detected opportunities.",
    "🛡️ Backtest ratios are numerically bounded and non-finite metric values are safely handled before reaching the UI.",
    "📋 Completed backtest trades now expose timestamp, side, entry, exit, P/L and bars held as real backend data.",
    "🗂️ Signals and History date groups use consistent spacing and borders so headings and dates are never hidden or clipped.",
    "📱 Mobile navigation and page cards were reduced for less visual clutter while preserving the five existing destinations.",
    "💾 Production market-data cache now verifies Supabase health and reuses persistent Yahoo candles across restarts.",
    "📡 Yahoo rate-limit backoff is isolated per symbol and cached data is reused during backoff when available.",
    "🧹 Runtime artifacts such as __pycache__, .pyc files and local state databases are excluded from merge history.",
    "📚 Release information now has one canonical source shared by Dashboard, Telegram and generated repository documentation.",
)

def markdown_whats_new() -> str:
    lines = [f"# What's New — MULTIBOT2 v{APP_VERSION}", "", "Generated from release_notes.py.", ""]
    lines.extend(f"- {item}" for item in RELEASE_HIGHLIGHTS)
    return "\n".join(lines) + "\n"

def telegram_whats_new() -> str:
    body = "\n".join(f"• {item}" for item in RELEASE_HIGHLIGHTS)
    return f"🆕 *WHAT'S NEW — MULTIBOT2 v{APP_VERSION}*\n━━━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━━━"

__all__ = ["APP_VERSION", "RELEASE_HIGHLIGHTS", "markdown_whats_new", "telegram_whats_new"]
