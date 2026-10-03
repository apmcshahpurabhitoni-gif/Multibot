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


def test_fills_use_the_declared_depth_surfaces():
    """``geometry.md`` §7: surfaces alternate by nesting depth.

    depth 0 section/workspace -> ``--surface``  + outer radius
    depth 1 gutter/panel      -> ``--f-inner-bg`` (== ``--surface-2``)
    depth 2 row/tile/control  -> ``--surface``

    and: "A card may never be painted the same colour as the surface it sits on."

    Fills must come from those tokens. A literal ``rgb()``/``#hex`` in a
    component rule is the failure this catches: it cannot follow the theme, so
    the same card renders white on a dark surface, and it silently drifts apart
    from its neighbours -- which is what left depth-1 boxes split between white
    and grey across tabs.

    Contrast tokens stay governed by ``test_contrast_tokens.py``; this only
    checks that fills are tokenised, never which token a given rule picked.
    """
    import re

    FILL_PROPS = ("background", "background-color")
    tokenised = re.compile(r"var\(\s*--(surface|f-surface|bg)[a-z0-9-]*\s*\)")

    offenders = []
    for name in ("styles.css", "foundation.css", "appearance-overrides.css"):
        source = re.sub(r"/\*.*?\*/", "", (ROOT / name).read_text(encoding="utf-8"), flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
            selector = " ".join(selector.split())
            # Blocks that DECLARE custom properties are where literals belong:
            # that is the token layer itself (:root, html[data-theme=...]).
            if re.search(r"--[a-z0-9-]+\s*:", body):
                continue
            for prop in FILL_PROPS:
                for value in re.findall(prop + r"\s*:\s*([^;}]+)", body):
                    if value.strip().startswith("var("):
                        continue
                    # transparent / none / gradients carry no surface identity.
                    if re.match(r"\s*(transparent|none|inherit|initial)", value):
                        continue
                    if "gradient(" in value:
                        continue
                    # A literal paint means the rule opted out of the depth
                    # language. Named colours used as accents are fine.
                    if re.match(r"\s*(red|blue|green|white|black|orange|purple|grey|gray|"
                                 r"yellow|pink|cyan|magenta|teal|navy|silver|maroon)\b", value):
                        continue
                    # Scrims (modal / drawer backdrops) are alpha, not a surface.
                    if re.match(r"\s*rgba\([^)]*,\s*(0?\.\d+|0)\s*\)", value, re.I):
                        continue
                    if re.match(r"\s*(#[0-9a-f]{3,8}|rgba?\(|hsla?\()", value, re.I):
                        offenders.append(f"{name}: `{selector[-52:]}` -> {prop}:{value.strip()[:24]}")
    assert not offenders, (
        "component rules must paint with surface tokens, not literal colours:\n"
        + "\n".join(offenders[:40])
        + ("\n... and %d more" % (len(offenders) - 40) if len(offenders) > 40 else "")
    )


def test_border_radius_uses_the_declared_tier_tokens():
    """Radius must come from the three tiers, not from a literal.

    ``docs/DESIGN_SYSTEM/geometry.md`` declares exactly three tiers -- outer
    ``--radius``/``--ui-outer-r``, inner ``--radius-sm``/``--ui-inner-r``,
    control ``--ui-control-r``/``--ui-collapse-radius`` -- plus ``--radius-xs``
    and full pills, and states that "any other literal radius is a defect".

    The reason it matters is not pedantry: the tiers differ per style (outer
    14/10/16, inner 11/8/8). A literal pins the Modern value, so a hardcoded
    12px or 11px silently ignores Neo and Material 3 -- which is exactly how the
    Tools cards ended up at 18px while every other page used 14px, and why
    neighbouring boxes looked mismatched with no rule that appeared wrong.

    LEGACY_LITERALS is the remaining debt, listed so it cannot grow silently.
    Each entry is a value that should become a tier token; the guard fails if a
    value outside this list appears, and the list only shrinks.
    """
    import re

    # Shapes the tiers deliberately do not cover.
    SHAPE_EXEMPT = {"0", "0px"}
    # Scrollbar thumbs are sized to the track, not to a tier.
    SHAPE_EXEMPT.add("99px")
    # Full pills are legitimately used across the codebase (.signal-tab,
    # .backtest-rating, b.fresh, status dots) and nothing in the stylesheet says
    # which selector is a pill, so this value cannot be scoped. Known gap: a card
    # given 999px would pass. Tighten only alongside a pill-role class.
    SHAPE_EXEMPT.update({"999px", "50%"})

    # Values still hardcoded in the sheets. Treat as a punch list, not a
    # permission: each is a real off-contract radius awaiting its token.
    LEGACY_LITERALS = {
        "12px": "Tools runtime gutters, calendar items and category labels",
        "10px": "controls that should use var(--ui-control-r)",
        "11px": "boxes that should use var(--ui-inner-r)",
        "14px": "outer boxes that should use var(--radius)",
        "9px":  "inline chips that should use var(--radius-xs)",
        "8px":  "Neo/Material inner values hardcoded into shared rules",
        "6px":  "Neo/Material xs values hardcoded into shared rules",
        "4px":  "Material xs values hardcoded into shared rules",
        "5px":  "appearance swatch (12px dot, deliberately squircle)",
        "7px":  "small glyph containers (direction icon, calendar source)",
    }

    tier_tokens = ("--ui-outer-r", "--ui-inner-r", "--ui-control-r",
                   "--ui-collapse-radius", "--radius", "--radius-sm", "--radius-xs")

    offenders = []
    for name in ("styles.css", "foundation.css", "appearance-overrides.css"):
        source = (ROOT / name).read_text(encoding="utf-8")
        # Drop comments so the prose above does not register as a declaration.
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
            selector = " ".join(selector.split())
            for value in re.findall(r"border(?:-[a-z]+)*-radius\s*:\s*([^;}]+)", body):
                if any(token in value for token in tier_tokens):
                    continue
                for literal in re.findall(r"\b\d+(?:\.\d+)?px\b|\b\d+%", value):
                    if literal in SHAPE_EXEMPT or literal in LEGACY_LITERALS:
                        continue
                    offenders.append(f"{name}: {literal} on `{selector[-60:]}`")

    assert not offenders, (
        "radius values outside the declared tiers and the tracked legacy list:\n"
        + "\n".join(offenders)
        + "\nUse var(--radius) / var(--ui-outer-r), var(--radius-sm) / "
          "var(--ui-inner-r), var(--ui-control-r) / var(--ui-collapse-radius) "
          "or var(--radius-xs)."
    )


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


def test_no_dashed_or_dotted_borders_anywhere():
    """Every boundary in the dashboard is a solid hairline.

    ``.empty-state`` shipped with ``border:2px dashed var(--line-strong)`` --
    a dashed outline being the conventional "nothing here yet" placeholder. It
    was the ONLY dashed or dotted border in the codebase, so the one box drawn
    in a different border language was the empty state. It also hardcoded 2px
    (bypassing ``--border-w``) while sitting inside grey gutters that carry no
    outline at all, which is what made History read as inconsistent: white
    metric tiles with a solid hairline directly above a white dashed tile.

    Comments are stripped before scanning -- the override explains this defect
    in prose and the word "dashed" appears there on purpose.
    """
    import re

    sheets = {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in ("styles.css", "foundation.css", "appearance-overrides.css")
    }
    offenders = []
    for name, source in sheets.items():
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        for match in re.finditer(
            r"border(?:-top|-right|-bottom|-left)?\s*:[^;}]*?\b(dashed|dotted)\b",
            code,
        ):
            offenders.append(f"{name}: {match.group(0).strip()[:70]}")
    assert not offenders, (
        "dashed/dotted borders reintroduced (every boundary is a solid "
        "hairline):\n" + "\n".join(offenders)
    )

    # Rule-precise, not a bare substring: the replacement has to stay attached
    # to the empty-state rule, including the History variant that actually
    # renders there.
    assert (
        "html .empty-state,\n"
        "html #page-history .history-empty-state,\n"
        "html #page-overview .overview-activity .empty-state{\n"
        "  border:var(--border-w) solid var(--line)!important;"
        in sheets["appearance-overrides.css"]
    ), (
        "empty states must be solid --border-w hairlines like every other "
        "content tile; --border-w keeps Neo's 2px without a second hardcoded rule"
    )


def test_expanded_signal_cells_have_no_positional_hairlines():
    """The expanded signal's interior draws tiles, not a half-drawn table.

    ``foundation.css`` sets the detail cells to ``border:0``, then the next two
    rules put hairlines straight back with ``nth-child(even)`` /
    ``nth-child(n+3)``. Those lines are the interior rules of a bordered table
    and only made sense against the frame the grid used to carry. With the
    frame gone they render as fragments: no top edge on the first row, no right
    or bottom edge anywhere. Measured at 390px that came back as cell 1 with no
    border, cell 2 with a left edge, cell 3 with a top edge, cell 4 with both --
    the "some have a border, some don't" read.

    They are also positional, so the pattern is wrong at whichever breakpoint
    changes the column count (the grid is 3 / 2 / 1 columns). The final layer
    therefore has to neutralise every hairline variant that ever won the
    cascade, and separate the tiles with a gap instead.
    """
    import re

    code = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    variants = (":nth-child(even)", ":nth-child(n+3)")
    checked = 0
    for selector_text, body in re.findall(r"([^{}]+)\{([^{}]*)\}", code):
        for one in (s.strip() for s in selector_text.split(",")):
            if "detail-grid>div" not in one:
                continue
            if not any(v in one for v in variants):
                continue
            assert "border:0!important" in body, (
                f"{one} still reintroduces a positional hairline; the final "
                f"layer must neutralise it with border:0!important"
            )
            checked += 1
    assert checked >= 8, (
        f"expected the hairline overrides to cover both pages, both collapsed "
        f"and expanded, in both interface styles; only found {checked}"
    )

    # Tiles are separated by the gutter showing through, not by lines.
    assert (
        "html[data-style=\"neo\"] #page-overview .overview-signals .signal-card.expanded .detail-grid{\n"
        "  gap:6px!important;" in code
    ), "the detail grid must separate its cells with a gap, not with borders"
