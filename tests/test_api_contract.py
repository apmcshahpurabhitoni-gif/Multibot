"""API contract guard.

``docs/API.md`` is the specification a front-end rebuild is written against, and
``docs/THEME_SYSTEM.md`` is the specification for the 30 theme combinations.

Before these documents existed the only record of the payload shape was the
rendering code in ``app.js``, which meant the implementation and the
specification were the same file and neither could be changed safely.

These tests assert that the documentation still describes the code. Editing the
server without updating ``docs/API.md`` fails CI, and vice versa.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard import build_dashboard_snapshot
from signal_lifecycle import dashboard_signal

MAIN = ROOT / "main.py"
APPEARANCE = ROOT / "appearance.js"
API_DOC = ROOT / "docs" / "API.md"
THEME_DOC = ROOT / "docs" / "THEME_SYSTEM.md"
REBUILD_BRIEF = ROOT / "docs" / "REBUILD_BRIEF.md"
LOCKED_RULES = ROOT / "docs" / "LOCKED_RULES.md"

# Documented in docs/API.md §2 and asserted to exist in main.py.
JSON_ROUTES = [
    "/ping",
    "/api/health",
    "/api/dashboard",
    "/api/diagnostics/sweep",
    "/api/calendar",
    "/api/news",
    "/api/backtest",
]

# docs/API.md §6, from dashboard.build_dashboard_snapshot().
ENVELOPE_KEYS = [
    "ok", "version", "whats_new", "generated_at", "backtest_assets",
    "system", "rules", "universe", "strategies", "accounts", "signals",
    "trades", "scan", "scan_history", "health", "counts", "signal_summary",
]

# docs/API.md §7, the fields dashboard_signal() adds to the stored event row.
SIGNAL_COMPUTED_FIELDS = [
    "entry", "stop_loss", "take_profit", "freshness", "age_minutes",
    "send_count", "first_sent_at", "last_sent_at", "delivery",
    "has_trade_levels", "actionable",
]

STYLES = ["modern", "material3", "neo"]
ACCENTS = ["emerald", "indigo", "amber", "rose", "cyan"]
THEMES = ["light", "dark"]


def _main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def _api_doc() -> str:
    assert API_DOC.is_file(), "docs/API.md is required: it is the UI rebuild contract"
    return API_DOC.read_text(encoding="utf-8")


def _event() -> dict:
    return {
        "signal_id": "abc",
        "signal_key": "adaptive_trend|BTC-USD|BUY",
        "strategy": "adaptive_trend",
        "version": "1.0.0",
        "symbol": "BTC-USD",
        "direction": "BUY",
        "timestamp": "2026-10-01T09:00:00+05:30",
        "timeframe": "1d",
        "reason": "test",
        "pipeline_status": "RECORDED",
        "metadata": {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0},
    }


# --- routes ---------------------------------------------------------------

def test_every_documented_route_exists_in_the_server():
    source = _main_source()
    for route in JSON_ROUTES:
        assert f'"{route}"' in source, f"main.py no longer references route {route}"


def test_static_assets_served_by_main_are_documented():
    source = _main_source()
    match = re.search(r"files=\{(.*?)\}", source, re.S)
    assert match, "static file map not found in main.py::web_server"
    served = set(re.findall(r'"(/[^"]*)":\("([^"]+)"', match.group(1)))
    served_paths = {path for path, _ in served}
    served_files = {name for _, name in served}
    doc = _api_doc()
    for path in served_paths:
        assert path in doc, f"docs/API.md does not document served route {path}"
    for name in served_files:
        assert name in doc, f"docs/API.md does not document served asset {name}"


def test_api_doc_lists_every_route():
    doc = _api_doc()
    for route in JSON_ROUTES:
        assert route in doc, f"docs/API.md route table is missing {route}"


def test_query_parameters_documented_match_the_server():
    """The client cannot discover a parameter name it was never told about."""
    source = _main_source()
    doc = _api_doc()
    for param in ("period", "strategy", "symbol", "date", "impact", "refresh"):
        assert f'"{param}"' in source, f"main.py no longer reads query param {param}"
        assert f"`{param}`" in doc, f"docs/API.md does not document query param {param}"


# --- payload envelope -----------------------------------------------------

def test_dashboard_envelope_has_every_documented_key():
    snapshot = build_dashboard_snapshot()
    missing = [key for key in ENVELOPE_KEYS if key not in snapshot]
    assert not missing, f"/api/dashboard is missing documented keys: {missing}"


def test_envelope_does_not_grow_without_documentation():
    """A new field is a safe change, but it must be written down."""
    snapshot = build_dashboard_snapshot()
    undocumented = sorted(set(snapshot) - set(ENVELOPE_KEYS))
    assert not undocumented, (
        f"undocumented envelope keys: {undocumented}. Add them to docs/API.md §6 "
        f"and ENVELOPE_KEYS in this test."
    )


def test_system_block_echoes_the_locked_rules():
    """The UI must read these, never hardcode them."""
    snapshot = build_dashboard_snapshot()
    system = snapshot["system"]
    assert system["mode"] == "PAPER"
    assert system["timezone"] == "Asia/Kolkata"
    assert system["provider"] == "YAHOO"
    assert system["freshness_hours"] == 1
    assert system["leverage"] == 1.0
    assert snapshot["rules"]["account_size_inr"] == 100_000
    assert snapshot["rules"]["risk_per_trade_inr"] == 2_000


def test_accounts_block_matches_the_locked_config():
    """docs/API.md §6 and LOCKED_RULES.md §3 list the accounts. Keep them honest."""
    from config import ACCOUNT_NAMES, ACCOUNT_TRADE_LIMITS

    snapshot = build_dashboard_snapshot()
    assert snapshot["accounts"]["names"] == list(ACCOUNT_NAMES)
    assert snapshot["rules"]["account_trade_limits"] == ACCOUNT_TRADE_LIMITS

    for name in ACCOUNT_NAMES:
        assert name in LOCKED_RULES.read_text(encoding="utf-8"), (
            f"docs/LOCKED_RULES.md omits account {name}"
        )
        assert name in _api_doc(), f"docs/API.md omits account {name}"


def test_universe_count_matches_the_locked_asset_count():
    """25 assets is a locked rule, not a coincidence."""
    from config import LIVE_ASSETS

    snapshot = build_dashboard_snapshot()
    assert snapshot["universe"]["count"] == 25
    assert snapshot["universe"]["count"] == len(LIVE_ASSETS)


def test_signal_computed_fields_are_produced():
    enriched = dashboard_signal(_event())
    missing = [f for f in SIGNAL_COMPUTED_FIELDS if f not in enriched]
    assert not missing, f"dashboard_signal() no longer produces: {missing}"


def test_actionable_requires_levels_and_freshness():
    """docs/API.md §7 documents this predicate; it is the flag the UI renders."""
    fresh_with_levels = dashboard_signal(_event())
    assert fresh_with_levels["has_trade_levels"] is True
    assert fresh_with_levels["actionable"] is True

    no_levels = _event()
    no_levels["metadata"] = {}
    degraded = dashboard_signal(no_levels)
    assert degraded["has_trade_levels"] is False
    assert degraded["actionable"] is False, (
        "a signal without trade levels must never be actionable"
    )


def test_a_malformed_signal_never_raises():
    """One bad historical row must not 500 the dashboard API."""
    broken = _event()
    broken["timestamp"] = "not-a-timestamp"
    result = dashboard_signal(broken)
    assert result["freshness"] == "STALE"
    assert result["age_minutes"] == 0


# --- theme system ---------------------------------------------------------

def test_theme_doc_lists_every_style_accent_and_theme():
    doc = THEME_DOC.read_text(encoding="utf-8")
    for value in STYLES + ACCENTS + THEMES:
        assert value in doc, f"docs/THEME_SYSTEM.md never mentions {value}"


def test_theme_doc_covers_all_thirty_combinations():
    doc = THEME_DOC.read_text(encoding="utf-8")
    assert "30" in doc, "docs/THEME_SYSTEM.md must state the 30-combination matrix"


def test_appearance_js_options_match_the_documented_axis():
    """STYLES/ACCENTS in appearance.js define the axis; the doc must agree."""
    source = APPEARANCE.read_text(encoding="utf-8")
    styles = re.search(r"const STYLES=\[([^\]]*)\]", source)
    accents = re.search(r"const ACCENTS=\[([^\]]*)\]", source)
    assert styles and accents, "appearance.js axis definitions not found"
    parsed_styles = re.findall(r'"([^"]+)"', styles.group(1))
    parsed_accents = re.findall(r'"([^"]+)"', accents.group(1))
    assert parsed_styles == STYLES
    assert parsed_accents == ACCENTS


def test_theme_attributes_are_present_on_the_html_element():
    """data-theme / data-style / data-accent are how every theme rule matches."""
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    tag = re.search(r"<html[^>]*>", html)
    assert tag, "<html> element not found in dashboard.html"
    element = tag.group(0)
    for attribute, default in (
        ("data-theme", "light"), ("data-style", "modern"), ("data-accent", "emerald")
    ):
        assert f'{attribute}="{default}"' in element, (
            f"<html> must ship {attribute}=\"{default}\" as the server-rendered default"
        )


def test_contrast_tokens_are_declared_only_by_the_base_sheet():
    """Load-bearing invariant: a later sheet redefining a contrast token breaks
    exactly one style/accent/theme combination. See THEME_SYSTEM.md §1."""
    contrast_tokens = (
        "--positive", "--negative", "--warning",
        "--accent", "--on-accent", "--accent-fill",
    )
    for sheet in ("foundation.css", "appearance-overrides.css"):
        text = (ROOT / sheet).read_text(encoding="utf-8")
        for token in contrast_tokens:
            assert f"{token}:" not in text, (
                f"{sheet} re-declares {token}; only styles.css owns contrast tokens"
            )


# --- brief completeness ---------------------------------------------------

def test_rebuild_brief_links_the_contracts_it_depends_on():
    brief = REBUILD_BRIEF.read_text(encoding="utf-8")
    for name in ("API.md", "LOCKED_RULES.md", "THEME_SYSTEM.md"):
        assert name in brief, f"docs/REBUILD_BRIEF.md must link {name}"


def test_locked_rules_document_exists_and_covers_the_invariants():
    assert LOCKED_RULES.is_file()
    text = LOCKED_RULES.read_text(encoding="utf-8")
    for value in ("100,000", "2,000", "25", "1.0", "Asia/Kolkata", "yahoo"):
        assert value in text, f"docs/LOCKED_RULES.md omits locked value {value}"