from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
CSS = (ROOT / "appearance-overrides.css").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
APPEARANCE = (ROOT / "appearance.js").read_text(encoding="utf-8")
STYLES = (ROOT / "styles.css").read_text(encoding="utf-8")


def test_appearance_has_separate_theme_and_interface_style_controls():
    assert 'id="themeToggle"' in HTML
    assert 'data-style-choice="modern"' in HTML
    assert 'data-style-choice="neo"' in HTML
    assert 'data-theme="light"' in HTML
    assert 'data-style="modern"' in HTML
    assert 'html[data-style="neo"]' in STYLES
    assert 'mavis-theme' in APPEARANCE
    assert 'mavis-style' in APPEARANCE


def test_appearance_bridge_is_loaded_after_app():
    assert '<script src="app.js" defer></script>' in HTML
    assert '<script src="appearance.js" defer></script>' in HTML
    assert HTML.index('app.js') < HTML.index('appearance.js')
    assert 'applyStyle' in APPEARANCE


def test_appearance_controls_are_compact_without_redesigning_shell():
    foundation = (ROOT / "foundation.css").read_text(encoding="utf-8")
    # The topbar utility buttons are ExpandableControl siblings: one size and one
    # radius from the foundation contract, and no per-viewport geometry override.
    assert '--ui-collapse-size:32px' in foundation
    assert '--ui-collapse-radius:10px' in foundation
    assert '--ui-control-h:var(--ui-collapse-size)' in CSS
    assert '--ui-control-r:var(--ui-collapse-radius)' in CSS
    assert '.topbar .icon-button{padding:0!important;border:2px solid var(--line)!important' in CSS
    assert '.topbar .icon-button{width' not in CSS
    # Neo supplies the flat ink treatment only; it must not resize the control.
    assert 'html.neo-mode .topbar .icon-button{\n  padding:0!important;' in CSS
    assert '.topbar .header-meta{display:flex;align-items:center;flex-wrap:nowrap' in CSS
    assert '@media(max-width:560px)' in CSS
    assert '.appearance-style-grid{display:grid' in CSS


def test_appearance_rows_are_not_targeted_by_type_position_selectors():
    """Positional selectors cannot address the appearance rows.

    The section heading is a ``<div>`` that precedes the rows, so it is the
    first div child. ``.settings-row:first-of-type`` therefore matches nothing
    at all -- it silently did nothing on every load. ``:nth-of-type(4)`` only
    reached the Accent row by coincidence of that same heading, and would
    silently retarget the day markup shifted.

    Both shipped that way, leaving the panel with no top edge and a blanket
    inner radius on rows that are meant to read as one continuous surface.
    """
    import re

    heading_at = HTML.find('<div class="section-heading">')
    first_row_at = HTML.find('<div class="settings-row">')
    assert heading_at != -1 and first_row_at != -1, (
        "expected both .section-heading and .settings-row in dashboard.html"
    )
    assert heading_at < first_row_at, (
        "expected .section-heading to precede the .settings-row siblings in "
        "dashboard.html; if that changed, revisit the positional selectors below"
    )

    sheets = {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in ("styles.css", "foundation.css", "appearance-overrides.css")
    }
    offenders = []
    for name, source in sheets.items():
        for selector in re.findall(r"([^{}]+)\{[^{}]*\}", source):
            selectors = [s.strip() for s in selector.split(",")]
            for one in selectors:
                # Strip comments that may precede the selector on the same line.
                one = one.split("*/")[-1].strip()
                if "settings-row" not in one:
                    continue
                if ":first-of-type" in one:
                    offenders.append(f"{name}: {one} can never match")
                elif re.search(r":nth-of-type\(\s*\d+\s*\)", one):
                    offenders.append(f"{name}: {one} targets a div position, not a row")
    assert not offenders, "positional selectors on .settings-row:\n" + "\n".join(offenders)

    # The panel must still be framed. These are asserted against the exact rule
    # text, not a bare selector substring: a loose check is satisfied by the
    # neighbouring margin rule, so it would still pass if the top border were
    # moved onto every row.
    assert (
        "#page-tools .tools-appearance>.section-heading+.settings-row{\n"
        "  border-top:1px solid var(--line)!important;" in sheets["styles.css"]
    ), (
        "the panel's top edge must be declared on the row after the heading; "
        "without it the panel has no top border and no top corners"
    )
    assert (
        "#page-tools .tools-appearance>.section-heading+.settings-row{\n"
        "  margin-top:8px!important;" in sheets["styles.css"]
    ), "the first settings row's top margin rule is no longer attached to the first row"
    assert (
        '.settings-row:has(.settings-inline[aria-label="Accent color"])'
        in sheets["appearance-overrides.css"]
    ), (
        "the Accent row must be targeted by its own label rather than div position"
    )


def test_neo_brutalism_covers_interactive_surface():
    for selector in (
        'html[data-style="neo"] .primary-button',
        'html[data-style="neo"] .secondary-button',
        'html[data-style="neo"] .icon-button',
        'html[data-style="neo"] .text-button',
        'html[data-style="neo"] .nav-button',
        'html[data-style="neo"] .filter-button',
        'html[data-style="neo"] .settings-toggle',
        'html[data-style="neo"] input',
        'html[data-style="neo"] select',
    ):
        assert selector in CSS
    assert ':hover' in CSS
    assert ':active' in CSS
