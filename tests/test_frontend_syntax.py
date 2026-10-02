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
ASSETS = ["app.js", "appearance.js", "dashboard-live-wiring.js"]

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


def test_stylesheet_load_order_is_preserved():
    """Later sheets win at equal specificity. Reordering silently restyles 30 combos."""
    import re

    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    order = re.findall(r'href="([a-z-]+\.css)\?[^"]*"', html)
    assert order == ["styles.css", "foundation.css", "appearance-overrides.css"], (
        f"stylesheet order changed to {order}; only styles.css may declare contrast tokens"
    )
