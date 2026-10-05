"""Frontend syntax guard.

The dashboard is plain static JavaScript with no bundler and no lint step, so a
single stray edit can make app.js fail to parse. The failure is silent and
severe: the whole file never executes, no render happens, and the page sits on
"CONNECTING" forever with no server-side error to explain it.

That is exactly what happened once already. An insertion anchored on
``function loadDashboard(){try{`` matched inside ``async function loadDashboard``
and consumed the ``async`` keyword, leaving a bare ``await`` in a non-async
function -- SyntaxError, dashboard dead, server logs clean.

``node --check`` parses a file without executing it. When node is available this
runs it over every shipped asset; otherwise the test skips rather than giving a
false green.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ["app.js", "appearance.js", "dashboard-live-wiring.js", "notifications.js"]

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@requires_node
@pytest.mark.parametrize("name", ASSETS)
def test_shipped_javascript_parses(name: str):
    path = ROOT / name
    assert path.is_file(), f"{name} is referenced by dashboard.html but missing"
    result = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{name} does not parse; the dashboard will render nothing.\n{result.stderr}"
    )


def test_async_functions_that_use_await_keep_their_keyword():
    """Cheap guard that runs even without node.

    ``loadDashboard`` awaits inside a try/catch. If the ``async`` keyword is ever
    dropped by a careless edit, the file stops parsing. The negative check uses a
    lookbehind because ``"function loadDashboard("`` is a substring of the valid
    ``"async function loadDashboard("``.
    """
    import re

    source = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "async function loadDashboard(" in source, (
        "loadDashboard uses await and must stay declared async"
    )
    assert not re.search(r"(?<!async )function loadDashboard\(\)", source), (
        "loadDashboard lost its async keyword; await is now a SyntaxError"
    )


def test_every_asset_in_dashboard_html_exists():
    """Each shipped asset must be referenced and present.

    Stylesheets carry a ``?v=`` cache-buster, so the reference is matched on the
    path alone.
    """
    import re

    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    assets = ASSETS + ["styles.css", "foundation.css", "appearance-overrides.css"]
    for name in assets:
        assert re.search(r'(?:src|href)="' + re.escape(name) + r'(?:\?[^"]*)?"', html), (
            f"dashboard.html no longer references {name}"
        )
        assert (ROOT / name).is_file(), f"{name} referenced but missing on disk"


def test_collapsed_signal_card_names_its_strategy():
    """The collapsed card must say which strategy produced the signal.

    ``signalCard()`` computed ``strategy`` but only rendered it inside the
    ``open?`` detail grid, so a reader had to expand all 500 cards to learn
    which strategy fired. History already led its sub-line with the strategy
    (``renderOpenHistoryRow``); this pins the signal card to the same
    convention so the two lists cannot drift apart again.
    """
    import re

    source = (ROOT / "app.js").read_text(encoding="utf-8")
    start = source.index("function signalCard(")
    end = source.index("\nfunction ", start + 10)
    body = source[start:end]

    summary = re.search(r"const summary=(.*?);(?=const|return)", body, re.S)
    assert summary, "signalCard no longer builds a collapsed `summary`"
    # The collapsed sub-line must lead with the strategy, not the direction:
    # the direction is already shown by .direction-icon and the .signal-side
    # badge, so the summary is where the strategy belongs. Both branches need
    # it -- a signal with no trade levels is exactly the one a reader has to
    # open, so hiding the strategy there would defeat the point.
    assert summary.group(1).count("${strategy}") == 2, (
        "both the with-levels and without-levels summaries must name the strategy"
    )
    # The aria-label is the accessible name and overrides the inner text, so a
    # screen-reader user would not hear the strategy unless it is named here too.
    assert re.search(r'aria-label="\$\{open\?"Collapse":"Expand"\} details for '
                     r'\$\{escapeHtml\(label\)\} from \$\{escapeHtml\(strategy\)\}"', body), (
        "the collapsed card's aria-label must name the strategy as well"
    )


def test_legacy_strategy_names_resolve_to_registered_strategies():
    """Signals stored before a display rename must still show the current name.

    ``bcb47ba``/``62d81b6``/``1eedaff`` renamed the three strategies' display
    names while keeping their ids and versions, so rows recorded earlier still
    carry the old name. ``app.js`` maps those old names onto the id and lets the
    registry supply the name.

    The map is cross-checked against the live registry on purpose: a typo in a
    strategy id would not raise an error, it would just fall through to the raw
    stored name and quietly reintroduce the label this exists to remove.
    """
    import json
    import re
    import sys

    sys.path.insert(0, str(ROOT))
    from strategies.registry import discover_strategies

    source = (ROOT / "app.js").read_text(encoding="utf-8")
    match = re.search(r"const LEGACY_STRATEGY_NAMES=Object\.freeze\((\{.*?\})\)", source, re.S)
    assert match, "app.js no longer declares LEGACY_STRATEGY_NAMES"
    aliases = json.loads(match.group(1))

    registered = {s.manifest.id: s.manifest.name for s in discover_strategies().all()}
    assert aliases, "the legacy-name map is empty; stored rows would show old names again"
    for legacy, strategy_id in aliases.items():
        assert strategy_id in registered, (
            f"legacy name {legacy!r} maps to {strategy_id!r}, which is not a "
            f"registered strategy; it would fall through to the raw stored name"
        )
        assert legacy != registered[strategy_id], (
            f"{legacy!r} is already the current name for {strategy_id!r}; the "
            f"mapping is dead weight and should be removed"
        )

    # strategyInfo must actually route through the map, not just declare it.
    info = re.search(r"function strategyInfo\(value\)\{(.*?)\}", source, re.S)
    assert info, "app.js no longer defines strategyInfo()"
    assert "LEGACY_STRATEGY_NAMES[value]" in info.group(1), (
        "strategyInfo() no longer resolves legacy names, so old rows show the "
        "stored name again"
    )


def test_stylesheet_load_order_is_preserved():
    """Later sheets win at equal specificity. Reordering silently restyles 30 combos."""
    import re

    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    order = re.findall(r'href="([a-z-]+\.css)\?[^"]*"', html)
    assert order == ["styles.css", "foundation.css", "appearance-overrides.css"], (
        f"stylesheet order changed to {order}; only styles.css may declare contrast tokens"
    )
