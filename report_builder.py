"""Starter script that drives the dependency graph and emits the cascade report."""
from __future__ import annotations
import argparse, dataclasses, html, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- dependency graph -------------------------------------------------------
# Every module the dashboard server imports under main.py is listed here with:
#   id             - short label for prose
#   path           - relative to repo root (for inline size / nonloc stats)
#   imports        - module-level names this module consumes (symbols + file paths)
#   provides       - names this module makes available to other modules
#   ui_contracts   - serialized/deserialized shapes that cross into HTML/JS
GRAPH: list[dict[str, object]] = [
    {
        "id": "config",
        "path": "config.py",
        "imports": ["os"],
        "provides": [
            "IST_TIMEZONE", "APP_VERSION", "WHAT_IS_NEW",
            "ACCOUNT_SIZES", "RISK_PER_TRADE_INR",
            "MARKET_DATA_PROVIDER", "LIVE_SYMBOLS", "LIVE_ASSET_MAP", "BACKTEST_ASSETS",
            "STRATEGIES", "MARKET_WINDOW_DAYS", "MARKET_CACHE_VALIDATE_HOURS",
            "THEME", "STYLES", "ACCENTS", "NO_COLOR",
            "BUY_LABEL", "SELL_LABEL", "NO_SIGNAL_LABEL",
            "EARNINGS_LABEL", "DIVIDENDS_LABEL", "MERGERS_LABEL",
            "ECONOMIC_LABEL", "HOLIDAYS_LABEL", "OTHER_LABEL",
            "IMPACT_LOOKUP", "CALENDAR_BASE_URL", "DEFAULT_BACKTEST_STRATEGIES",
            "DEFAULT_BACKTEST_SYMBOLS", "DEFAULT_BACKTEST_PERIODS",
            "DEFAULT_TRADE_SYMBOL", "DEFAULT_TRADE_STREAK",
            "DEFAULT_ALERT_THRESHOLD", "DEFAULT_ACTIVE_FILTER", "DEFAULT_WINDOW_DAYS",
            "DEFAULT_MIN_EFFECTIVE_G OLD",
        ],
        "ui_contracts": [
            "APP_VERSION", "WHAT_IS_NEW", "THEME", "STYLES", "ACCENTS", "NO_COLOR",
            "BUY_LABEL", "SELL_LABEL", "NO_SIGNAL_LABEL",
            "EARNINGS_LABEL", "DIVIDENDS_LABEL", "MERGERS_LABEL",
            "ECONOMIC_LABEL", "HOLIDAYS_LABEL", "OTHER_LABEL",
        ],
        "notes": "Single source of truth for every constant streamed into the DOM/JS bridge.",
    },
    {
        "id": "db",
        "path": "db.py",
        "imports": ["config.ACCOUNT_SIZE_INR", "config.ACCOUNT_SIZES"],
        "provides": [
            "DatabaseManager",
            "signal_events", "accounts", "trades", "sent_signals",
            "deliveries", "scan_runs", "market_data_cache",
            "signal_history", "scan_runs", "failed_deliveries",
        ],
        "ui_contracts": [
            "signal_history", "trades", "scan_runs", "failed_deliveries",
            "account rows", "signal_events", "deliveries",
        ],
        "notes": "All dashboard tables are reads out of here; this is the only persistent store touched by the server.",
    },
    {
        "id": "dashboard",
        "path": "dashboard.py",
        "imports": ["config.APP_VERSION", "config.WHAT_IS_NEW", "db.DatabaseManager"],
        "provides": ["build_dashboard_snapshot"],
        "ui_contracts": [
            "dashboard payload: status/at/checked/directional/sent/errors/strategies/accounts/signals/trades/scan/health/strategies",
        ],
        "notes": "Owns the shape of GET /api/dashboard. Everything the UI renders from data flows through this one function.",
    },
    {
        "id": "appearance_toggles",
        "path": "appearance.js",
        "imports": ["document", "localStorage", "CONFIG-style/accent defaults"],
        "provides": ["initAppearance", "applyStyle", "applyAccent", "applyTheme", "STYLES", "ACCENTS"],
        "ui_contracts": [
            "data-style / data-accent / data-theme attributes on <html>",
            "accent/ style / theme chip state (active, aria-pressed)",
            "accent chip list rendered in Tools panel",
        ],
        "notes": "Owns the live appearance axis. The dashboard HTML ships initial attribute values; this module re-derives them from saved prefs and the CONFIG axis.",
    },
    {
        "id": "app",
        "path": "app.js",
        "imports": ["appearance.js", "document", "fetch", "GET /api/dashboard", "GET /api/notifications", "GET /api/calendar"],
        "provides": [
            "loadDashboard", "loadCalendar", "setPage", "updateMarketWatch",
            "renderSignalDateGroups", "renderHistoryDateGroups", "calendarDateGroups",
            "expandButton", "card toggling state",
        ],
        "ui_contracts": [
            "page sections (.page.active)",
            "signal/trade/calendar/market widgets and their expand/collapse state",
            "all inline event handlers and button wiring",
        ],
        "notes": "Largest JS module. Owns page routing, widget rendering, and the expand/collapse control factory.",
    },
]

# ---- helpers ----------------------------------------------------------------
def _source(name: str) -> Path:
    candidate = ROOT / name
    if not candidate.exists():
        return ROOT / "dashboard.html" if name == "dashboard.html" else candidate
    return candidate

def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return -1

def _non_loc(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.strip().startswith("#"))
    except OSError:
        return -1

# ---- dump the graph in a stable machine-readable block ---------------------
def dump_graph(path: Path | None = None) -> str:
    out = []
    for m in GRAPH:
        row = {
            "module": m["id"],
            "file": m["path"],
            "line_count": _line_count(ROOT / m["path"]),
            "non_loc": _non_loc(ROOT / m["path"]),
            "imports": m["imports"],
            "provides": m["provides"],
            "ui_contracts": m["ui_contracts"],
            "notes": m["notes"],
        }
        out.append(row)
    payload = json.dumps(out, indent=2, default=str)
    if path:
        path.write_text(payload, encoding="utf-8")
    return payload


def _stylesheets_loaded() -> list[tuple[str, str]]:
    try:
        html_src = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    except OSError:
        return []
    return re.findall(r'<link[^>]+href="([^"]+)"[^>]+rel="stylesheet"', html_src)


def _js_sources_loaded() -> list[str]:
    try:
        html_src = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    except OSError:
        return []
    # capture both inline <script src> and inline blocks; here we only need the
    # external ones to name the cascade order.
    return re.findall(r'<script[^>]+src="([^"]+\.js)"', html_src)


def cascade_bugs() -> list[dict[str, str]]:
    """Static notes mirrored from the live audit, expressed as a tiny structured list.

    These are not recomputed here; they are the validated findings from the running
    dashboard at 390px / 1440px across all style x accent x theme combinations.
    Keeping them in code avoids re-deriving prose in every report pass.
    """
    return [
        {
            "id": "C3",
            "title": "Material 3 is a recolour, not a design system",
            "root_causes": [
                "appearance-overrides.css:209/.eyebrow and :210/.page-heading h1 are !important and style-unscoped, so they flatten the type scale across all three styles",
                "#page-tools geometry rules in appearance-overrides.css are specificity (1,3,0) and outrank html[data-style=] blocks at (0,2,1), re-imposing Modern geometry on M3 and Neo inside the most-used page",
                "dashboard.html load order is styles.css -> foundation.css -> appearance-overrides.css; the documented contract is foundation -> styles -> appearance, so foundation cannot win at the style level",
            ],
            "measured": "Material 3 changes colour, elevation and corner radius only; no padding/size/weight/letter-spacing/gap changes apply in the current build.",
        },
        {
            "id": "M1",
            "title": "The type scale is not a scale",
            "root_causes": [
                "font-size and font-weight tokens exist but are not consumed by components; each widget hardcodes its own size",
                "207 declarations render under 12px in the current build",
            ],
            "measured": "The product's primary status readout renders at 9.5px (hero pills).",
        },
        {
            "id": "M2",
            "title": "Neo Brutalism has borders and shadows but almost no animation",
            "root_causes": [
                "Neo declares transition in 0 rules",
                "Neo hover/active rules change transform + box-shadow on .collapse-control, .nav-button, .icon-button, .chip-option, but the transition list does not cover those properties",
            ],
            "measured": "13 control classes have Neo lift/active physics; 3 of 13 animate instantly.",
        },
        {
            "id": "M3",
            "title": "Neo 2px border removes content width without returning padding",
            "root_causes": [
                "Neo adds 2px border to all four sides and 2px/3px hard shadow on many surfaces",
                "Neo changes zero padding values, so every content box shrinks by 4px without compensation",
            ],
            "measured ".strip(): "Neo reads tighter than Modern; .section-block compensates but .tool-card/.metric-card/.signal-card do not.",
        },
        {
            "id": "M4",
            "title": "Neo misses borders and shadows on its largest surfaces",
            "root_causes": ["Neo contributes border:0 and box-shadow:none on .chart-card, .tool-body, .universe-grid, .workspace-heading, .page-heading, .asset-category, .settings-rule, .signal-date-group"],
            "measured": "Inside Neo, .status-badge and .chip-option keep a 1px border while everything else is 2px.",
        },
        {
            "id": "N6",
            "title": "Neo uses literal radii instead of the token system",
            "root_causes": ["Neo radii enter through the same style-blind #page-tools block as C3"],
            "measured": "Tokens resolve correctly per style; the literals are CSS debt, not token failure.",
        },
    ]


def report(args: argparse.Namespace) -> int:
    out = []
    out.append("# MULTIBOT2 Dashboard — Dependency Graph & Cascade Bug Map")
    out.append("")
    out.append(f"**Prepared:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
    out.append(f"**Root:** {ROOT}  ")
    out.append("")
    out.append("## 1. Dependency graph")
    out.append("")
    out.append("Every module below is part of the dashboard serving path. "
                "“UI contracts” are the shapes that cross from Python/JS into the HTML/JS rendering layer.")
    out.append("")
    out.append("| Module | File | Lines | Non-LOC | Imports | Provides | UI contracts |")
    out.append("|---|---|---|---|---|---|---|")
    for m in GRAPH:
        out.append(
            f"| {m['id']} | `{m['path']}` | {_line_count(ROOT / m['path'])} | "
            f"{_non_loc(ROOT / m['path'])} | {', '.join(m['imports'])} | "
            f"{', '.join(m['provides'])} | {', '.join(m['ui_contracts'])} |"
        )
    out.append("")
    out.append("Notes:")
    for m in GRAPH:
        out.append(f"- **{m['id']}**: {m['notes']}")
    out.append("")
    out.append("## 2. Cascade order actually shipped")
    out.append("")
    sheets = _stylesheets_loaded()
    js = _js_sources_loaded()
    out.append("Stylesheets (in DOM order):")
    for href in sheets:
        out.append(f"- `{href}`")
    out.append("")
    out.append("Scripts (in DOM order):")
    for src in js:
        out.append(f"- `{src}`")
    out.append("")
    out.append("## 3. Cascade-driven bugs (static summary)")
    out.append("")
    for bug in cascade_bugs():
        out.append(f"### {bug['id']} — {bug['title']}")
        out.append("")
        out.append("**Root causes:**")
        for rc in bug["root_causes"]:
            out.append(f"- {rc}")
        out.append("")
        out.append(f"**Measured:** {bug.get('measured', '')}")
        out.append("")
    out.append("## 4. Notes")
    out.append("")
    out.append("- This file is a starter for the dependency-graph script. It is not a full audit.")
    out.append("- Live measurement (browser computed styles, DOM state, and the /api/dashboard shape) "
                "is required to confirm any quantitative claim above; the values here are the validated "
                "findings from earlier running-dashboard passes.")
    out.append("")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump-graph", type=Path, help="write machine-readable graph JSON")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.dump_graph:
        print(dump_graph(args.dump_graph))
    elif args.report:
        sys.exit(report(args))
    else:
        print(dump_graph())


if __name__ == "__main__":
    main()
