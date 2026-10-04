"""Guards for the visual-consistency re-audit (2026-10-03).

Every defect here was visible on screen, and every fix removed a *superseded*
rule rather than adding a new one. The tests therefore assert both halves: the
replacement is present **and** the rule that used to win by accident is gone.

A bare substring check would be useless for most of these. Asserting that
``#page-tools .tool-settings .chip-option`` appears somewhere is satisfied by
the very selector whose absence caused the bug, so the chip test below compares
the *set of properties* each card's selector declares and requires them to
match. Asserting ``padding:8px 10px`` is present would pin the defect, so the
compact test pins the absence of the old value alongside the new one.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
SHEETS = {
    "foundation.css": (ROOT / "foundation.css").read_text(encoding="utf-8"),
    "styles.css": (ROOT / "styles.css").read_text(encoding="utf-8"),
    "appearance-overrides.css": (ROOT / "appearance-overrides.css").read_text(encoding="utf-8"),
}
ALL_CSS = "\n".join(SHEETS.values())

# Properties that make up the chip box: size, spacing, type and colour. These
# are what made the two Tools cards render the same control two different ways.
CHIP_BOX_PROPERTIES = frozenset(
    {
        "min-height", "height", "padding", "padding-inline", "border-radius",
        "font-size", "line-height", "font-weight", "box-sizing",
        "color", "background", "border-color", "-webkit-text-fill-color",
    }
)


def _iter_rules(css, media="none"):
    """Yield ``(prelude, body, media)`` for every rule, with at-rule context.

    Without the context a responsive override looks like a duplicate of the
    base rule it legitimately replaces, which is the mistake these guards are
    meant to catch in the other direction.
    """
    prelude = ""
    index, length = 0, len(css)
    while index < length:
        char = css[index]
        if char == "{":
            depth, cursor = 1, index + 1
            while cursor < length and depth:
                if css[cursor] == "{":
                    depth += 1
                elif css[cursor] == "}":
                    depth -= 1
                cursor += 1
            body = css[index + 1 : cursor - 1]
            head = " ".join(prelude.split())
            if head.startswith("@"):
                match = re.match(r"@media\(([^)]*)\)", head)
                yield from _iter_rules(body, match.group(1) if match else head)
            else:
                yield head, body, media
            prelude = ""
            index = cursor
            continue
        if char != "}":
            prelude += char
        else:
            prelude = ""
        index += 1


def _declarations(body):
    """Map property -> value for one rule body, ignoring nested at-rules."""
    out = {}
    depth, current = 0, ""
    chunks = []
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == ";" and depth == 0:
            chunks.append(current)
            current = ""
        else:
            current += char
    chunks.append(current)
    for chunk in chunks:
        if ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        prop = prop.strip().lower()
        if prop and not prop.startswith("--"):
            out[prop] = " ".join(value.split()).lower()
    return out


def _selectors(prelude):
    # A prelude accumulates any comment that precedes the rule, so strip them
    # before comparing or `/* note */ .selector` never equals `.selector`.
    prelude = re.sub(r"/\*.*?\*/", " ", prelude, flags=re.S)
    return [s.strip() for s in prelude.split(",") if s.strip()]


def _properties_for_selector(sheet, selector):
    """Every property declared for an exact selector token in one sheet."""
    found = set()
    for prelude, body, _media in _iter_rules(SHEETS[sheet]):
        if selector not in _selectors(prelude):
            continue
        found |= set(_declarations(body))
    return found


def _declarations_for_selector(sheet, selector, prop):
    """Every value `prop` is given to an exact selector token in one sheet."""
    values = []
    for prelude, body, _media in _iter_rules(SHEETS[sheet]):
        if selector not in _selectors(prelude):
            continue
        value = _declarations(body).get(prop)
        if value is not None:
            values.append(value)
    return values


def test_tools_cards_declare_the_same_chip_contract():
    """The settings card must declare exactly the chip box the appearance card does.

    Measured defect: on the Tools page, "Workspace settings" chips rendered at
    9.5px / 5px 9px while "Accounts, assets and routing" -- the card added with
    the plug-and-play settings -- rendered at 11px / 7px 12px, because the new
    card was never enrolled in the small-text and chip-geometry contracts that
    the appearance card's selectors belong to. Comparing the declared property
    sets (rather than searching for one selector) means the new card cannot be
    added to only some of those rules and drift again.
    """
    appearance = _properties_for_selector(
        "appearance-overrides.css", "#page-tools .tools-appearance .chip-option"
    )
    settings = _properties_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .chip-option"
    )

    assert appearance, "the appearance card no longer declares any chip geometry"
    box = appearance & CHIP_BOX_PROPERTIES
    assert box, "no chip box properties found on the appearance card selector"

    missing = box - settings
    assert not missing, (
        "the settings card's chip selector is missing properties that the "
        f"appearance card declares: {sorted(missing)}. Both cards must declare "
        "the same chip box or they render the same control two different ways."
    )


def test_tools_card_label_and_hint_share_the_small_text_step():
    """Group labels inside the settings card must use the same 9.5px step.

    The 9.5px small-text contract is a single grouped rule; the settings card
    was missing from it, so its "Accounts" / "Assets" / "New York session" labels
    rendered at 12px beside 9.5px labels in every other Tools card.
    """
    grouped = [
        prelude
        for prelude, body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if _declarations(body).get("font-size") == "9.5px!important"
    ]
    # The contract is the widest of the 9.5px rules; a narrower one that shares
    # the value is a page refinement, not the grouped contract.
    widest = max(grouped, key=lambda p: len(_selectors(p)), default=None)
    assert widest, "the 9.5px small-text contract rule was not found"
    selectors = set(_selectors(widest))
    assert len(selectors) > 5, (
        "the 9.5px small-text contract should be one grouped rule covering every "
        f"small label on the dashboard, found only {len(selectors)} selectors"
    )
    for required in (
        "html #page-tools .tool-settings .settings-label",
        "html #page-tools .tool-settings .chip-option",
    ):
        assert required in selectors, (
            f"{required} is not enrolled in the 9.5px small-text contract; a new "
            "Tools card that skips it renders larger labels than its neighbours"
        )


def test_home_metric_tiles_reserve_one_height():
    """Every Home metric tile is the same height, so the grid rows cannot step.

    Measured defect: the Home grid had a 40px row and a 32px row. Below 560px
    the label is allowed to wrap rather than be ellipsised, and a wide value
    ("Rs 4,00,000") narrowed the label column until "ACCOUNT VALUE" wrapped,
    making that tile 8px taller than its three row-mates. Reserving the wrapped
    height on every tile is what keeps the rows aligned.
    """
    values = _declarations_for_selector("foundation.css", "#page-overview .metric-card", "min-height")
    assert "40px" in values, (
        "the Home metric card must reserve min-height:40px, found "
        f"{values!r}; without it a wrapped label makes one grid row taller "
        "than the next and the tile grid reads as ragged"
    )


def test_metric_label_is_not_capped_by_a_dead_flex_era_width():
    """The base label rule must not reintroduce a width cap.

    `.metric-card` is a two-column grid. The old `max-width:55%` was a flex-era
    cap that no longer constrained anything -- Home overrides it with 100% (and
    `none` under 560px) and Calendar pins its own -- so it only risked squeezing
    a label for no reason.
    """
    for prelude, body, _media in _iter_rules(SHEETS["styles.css"]):
        if ".metric-card span" not in _selectors(prelude):
            continue
        properties = _declarations(body)
        assert "max-width" not in properties, (
            f"`{prelude}` re-declares max-width on the metric label; the cap is "
            "dead and can only squeeze a label out of its column"
        )


def _compact_rules():
    """(sheet, prelude, properties) for every compact-mode rule."""
    for sheet, css in SHEETS.items():
        for prelude, body, _media in _iter_rules(css):
            if 'data-compact="true"' in prelude:
                yield sheet, prelude, _declarations(body)


def test_compact_mode_never_enlarges_a_surface():
    """Compact must shrink, never grow, and must not resurrect the dead rules.

    Measured defect: the toggle made Home 8px taller and History 14px taller
    and left Calendar and Tools byte-identical, because (a) a compact
    `.metric-card` padding of 8px exceeded the 7px normal value, (b) a 90px
    compact `.empty-state` floor exceeded the 76px natural height, (c) an
    `.section-block`/`.tool-card` rule in the override layer outranked and
    duplicated the real one, and (d) every Tools target lost to an id-scoped
    rule. Each of those is now pinned in both directions.
    """
    compact = list(_compact_rules())

    metric = [
        properties for _sheet, prelude, properties in compact
        if 'html[data-compact="true"] .metric-card' in _selectors(prelude)
    ]
    assert len(metric) == 1, "expected exactly one compact .metric-card rule"
    assert metric[0].get("padding") == "6px 9px!important", (
        "compact .metric-card padding must be smaller than the 7px normal "
        f"value, found {metric[0].get('padding')!r}"
    )

    empty = [
        properties for _sheet, prelude, properties in compact
        if 'html[data-compact="true"] .empty-state' in _selectors(prelude)
    ]
    assert len(empty) == 1, "expected exactly one compact .empty-state rule"
    assert empty[0].get("min-height") == "56px!important", (
        "an empty state is 76px tall; a 90px compact floor made every one of "
        f"them 14px taller than normal, found {empty[0].get('min-height')!r}"
    )

    for _sheet, prelude, _properties in compact:
        for selector in _selectors(prelude):
            target = re.split(r"[\s>+~:]", selector.lstrip("*#."))
            assert not any(part == "tool-card" for part in target), (
                f"`{selector}` re-adds a compact .tool-card padding. The Tools "
                "card is a 0-padding shell whose .tool-body carries the padding, "
                "so this can only make the page taller"
            )


def test_compact_rules_that_target_the_tools_page_carry_its_id():
    """A compact selector must out-specify the id-scoped rule it competes with.

    This is the root cause of the Tools page ignoring Compact entirely:
    `html[data-compact="true"] X` can never beat `#page-tools Y` (an id outranks
    an attribute plus a class), so those rules were silently dead. Whichever
    compact rule targets a class that the Tools page also styles by id must
    therefore repeat the `#page-tools` scope.
    """
    tools_scoped = set()
    for sheet, css in SHEETS.items():
        for prelude, _body, _media in _iter_rules(css):
            for selector in _selectors(prelude):
                if selector.startswith("#page-tools "):
                    tools_scoped.add(selector)

    def _last(selector):
        """The final simple selector of a (possibly compound) selector."""
        parts = re.split(r"[\s>+~]", selector.strip())
        return parts[-1] if parts else ""

    def _tail(selector):
        """The part of a compact selector that has to survive id scoping."""
        return re.sub(r"^html(\[[^\]]*\])+", "", selector).strip()


    # Targets a `#page-tools`-scoped compact rule already covers. Those are
    # fine: the unscoped rule still serves the other four pages, and the scoped
    # one is what actually reaches the Tools page.
    covered = {
        _last(selector)
        for _sheet, prelude, _properties in _compact_rules()
        if "#page-tools" in prelude
        for selector in _selectors(prelude)
    }

    offenders = []
    for sheet, prelude, _properties in _compact_rules():
        for selector in _selectors(prelude):
            if "#page-tools" in selector or _last(selector) in covered:
                continue
            tail = _tail(selector)
            if tail and any(sel.startswith(f"#page-tools {tail}") for sel in tools_scoped):
                offenders.append(
                    f"{sheet}: `{selector}` loses to `#page-tools {tail}`, which "
                    "an id always outranks, and no `#page-tools` compact rule "
                    "covers it; repeat the id scope so Compact reaches Tools"
                )
    assert not offenders, (
        "compact rules that can never win against an id-scoped rule:\n  "
        + "\n  ".join(offenders)
    )


def test_settings_toggle_is_only_a_chip_variant_not_a_second_component():
    """`.settings-toggle` must not carry its own base component definition.

    Measured defect: the class named two different components. One was a 56px
    settings switch row with a `span`/`b`/`small`/`i` knob and no markup
    anywhere in the app; the other was a chip. Eleven properties fought between
    them and the chip won only because the later sheet happened to load last.
    """
    assert ".settings-toggle-list" not in ALL_CSS, (
        "`.settings-toggle-list` styled a settings switch list that no markup "
        "in dashboard.html or app.js has ever produced"
    )

    # Exactly one base definition, and it must be the chip. `:hover`, `:active`
    # and `.active` variants are legitimate hooks and are not counted.
    base = [
        (sheet, prelude, _declarations(body))
        for sheet, css in SHEETS.items()
        for prelude, body, _media in _iter_rules(css)
        if ".settings-toggle" in _selectors(prelude)
    ]
    assert len(base) == 1, (
        "`.settings-toggle` must have exactly one base definition, found "
        f"{len(base)}: {[p for _s, p, _d in base]}. Two base definitions is "
        "what let a 56px switch row and a chip fight over eleven properties."
    )
    sheet, prelude, properties = base[0]
    chip = [
        _declarations(body)
        for p, body, _media in _iter_rules(SHEETS["styles.css"])
        if ".chip-option" in _selectors(p)
    ]
    assert chip, "the base `.chip-option` rule was not found"
    box = CHIP_BOX_PROPERTIES & set(properties)
    assert box, f"{sheet} `{prelude.strip()}` declares no chip box properties"
    mismatch = {
        prop: (properties.get(prop), expected.get(prop))
        for prop, expected in ((p, chip[0]) for p in box)
        if prop != "color" and properties.get(prop) != expected.get(prop)
    }
    assert not mismatch, (
        f"{sheet} `{prelude.strip()}` must declare `.settings-toggle` exactly as "
        f"`.chip-option` does; these differ (settings-toggle vs chip): {mismatch}"
    )
    for switch_row_marker in ("border-bottom",):
        assert switch_row_marker not in properties, (
            f"{sheet} `{prelude.strip()}` still carries the switch-row property "
            f"`{switch_row_marker}`; that is the second component, not a chip"
        )

    for source, text in (("dashboard.html", HTML), ("app.js", APP)):
        for match in re.finditer(r'class="([^"]*\bsettings-toggle\b[^"]*)"', text):
            classes = match.group(1).split()
            assert "chip-option" in classes, (
                f"{source} uses `settings-toggle` without `chip-option`: "
                f"{match.group(1)!r}. With no chip base the button would have no "
                "border, fill or type styling at all"
            )


def test_calendar_agenda_status_is_not_declared_twice_in_one_layer():
    """No top-level rule may be fully restated by a later rule in the same sheet.

    Measured defect: `appearance-overrides.css` declared
    `#page-calendar .calendar-agenda-status` twice at top level. The first
    (padding 8px 12px, gap 8px) was superseded wholesale by the second
    (padding 10px var(--ui-pad-x), gap 10px), so it could only ever mislead the
    next reader about which values the component uses.
    """
    declarations = {}
    for prelude, body, media in _iter_rules(SHEETS["appearance-overrides.css"]):
        if media != "none":
            continue
        if "#page-calendar .calendar-agenda-status" not in _selectors(prelude):
            continue
        for prop in _declarations(body):
            declarations.setdefault(prop, 0)
            declarations[prop] += 1

    repeated = sorted(prop for prop, count in declarations.items() if count > 1)
    assert not repeated, (
        "these properties are declared more than once for the same selector at "
        f"top level in appearance-overrides.css: {repeated}. The superseded "
        "passes must be merged, not left in place to lose by load order"
    )


def test_universe_grid_declares_only_its_live_layout():
    """`.universe-grid` is a block of asset rows, not a grid.

    Measured defect: the block rule declared `display:grid` with one column and
    `gap:0`, plus `border:0`, `border-radius:0` and `overflow:visible`, while
    later rules in the same sheet declare `display:block`, a 1px border and a
    radius. Eleven mutually-overriding `!important` properties, one winner,
    chosen by document order rather than intent.
    """
    for sheet in SHEETS:
        for prelude, body, _media in _iter_rules(SHEETS[sheet]):
            if "#page-tools .universe-grid" not in _selectors(prelude):
                continue
            properties = _declarations(body)
            assert "display" not in properties or properties["display"] == "block!important", (
                f"{sheet} declares a dead layout for `.universe-grid`: "
                f"display:{properties.get('display')}. The asset rows are a block "
                "stack; only one layout declaration may exist"
            )
            for dead in ("grid-template-columns",):
                assert dead not in properties, (
                    f"{sheet} declares `{dead}` on a block container: "
                    f"{properties.get(dead)!r}"
                )


def test_no_universe_grid_rule_is_fully_superseded_in_one_sheet():
    """A `.universe-grid` rule must not restate what a later rule already sets."""
    rules = [
        (prelude, _declarations(body), media)
        for prelude, body, media in _iter_rules(SHEETS["styles.css"])
        if "#page-tools .universe-grid" in _selectors(prelude)
    ]
    for index, (prelude, properties, media) in enumerate(rules):
        if len(properties) < 3:
            # A one-property pass is a legitimate layering refinement; the defect
            # was a whole block of layout properties that could never win.
            continue
        for later_prelude, later, later_media in rules[index + 1 :]:
            if later_media != media:
                # A responsive override is a legitimate restatement of the base.
                continue
            superseded = set(properties) & set(later)
            if superseded == set(properties) and properties:
                assert False, (
                    f"`{prelude}` is fully superseded by the later "
                    f"`{later_prelude}` on {sorted(superseded)}; it can never "
                    "win and only misleads the next reader"
                )

# ---------------------------------------------------------------------------
# Round 3: the "BOT SETTINGS" card as it rendered on a 390px phone.
#
# The card had grown a second component system that nobody had declared: an
# unlabelled number field, an OS-native select, two identical grey buttons and
# a chevron on its own line. Each guard below pins the replacement and the
# absence of the rule that used to win by accident.
# ---------------------------------------------------------------------------


def _declarations_in_media(sheet, selector, prop, media):
    """Every value `prop` gets for an exact selector inside one media query.

    `_iter_rules` keeps the comment that precedes an at-rule in its prelude, so
    a documented `@media` block never looks like one. Comments are removed here
    so an at-rule is recognised wherever it sits.
    """
    values = []
    css = re.sub(r"/\*.*?\*/", " ", SHEETS[sheet], flags=re.S)
    for prelude, body, at_media in _iter_rules(css):
        if at_media != media or selector not in _selectors(prelude):
            continue
        value = _declarations(body).get(prop)
        if value is not None:
            values.append(value)
    return values


def test_tool_card_heading_keeps_its_controls_on_one_line():
    """A Tool card heading must not wrap: the chevron was dropping below it.

    Measured defect: foundation.css puts `flex-wrap:wrap` on every
    `.section-heading`. On a 390px phone the settings heading needed
    212 + 112 + 32 + 24 = 380px inside 336px of content, so the chevron moved to
    a second line and the heading measured 101px tall against 57px on every
    sibling. The Backtest card already escaped this by shrinking its tag; the
    settings card has to do the same, which is only possible once the heading
    itself refuses to wrap.
    """
    assert _declarations_for_selector(
        "appearance-overrides.css", "html #page-tools .tool-card>.section-heading", "flex-wrap"
    ) == ["nowrap!important"], (
        "every Tools card heading must re-assert `flex-wrap:nowrap`; "
        "foundation.css wraps `.section-heading`, so without this the collapse "
        "chevron falls onto a line of its own on a phone"
    )
    # The tag contract is one rule for every card. It used to be declared per
    # card, so the settings session tag rendered a 10px pill beside the Markets
    # card's 11px one and the Backtest tag was dropped entirely below 390px.
    tag = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-card>.section-heading .tool-tag", "font-size"
    )
    assert tag == ["10px!important"], (
        "every Tools card tag must take one small step, found "
        f"{tag!r}; at 11px the session tag is 112px wide and starves the title"
    )
    # A rule that names one Tools card and the tag is a per-card override. The
    # shared `status-badge / inline-status / tool-tag` pill group is not: it is
    # one contract for every pill on the dashboard.
    per_card_tag = [
        prelude
        for prelude, _body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if ".tool-tag" in prelude
        and ".tool-card" not in prelude
        and any(
            card in prelude
            for card in (
                ".tool-backtest", ".tool-settings", ".tools-appearance",
                ".tool-universe", ".tool-accounts", ".tool-rules", ".tool-runtime",
            )
        )
    ]
    assert not per_card_tag, (
        "a single card still claims its own `.tool-tag` geometry, which is how the "
        f"tags drifted apart in the first place: {per_card_tag}"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-collapse>.section-heading>div", "flex"
    ), "the heading title must be allowed to shrink instead of pushing the chevron out"


def test_tools_body_and_row_inset_add_up_to_the_heading_inset():
    """Every Tools card, and every row inside the settings card, shares one edge.

    Measured defect: one sheet gave the same heading `padding:12px
    var(--ui-pad-x)` and another gave it `padding:10px 14px`, so full-width
    cards and column cards started their text 4px apart; the expanded body
    added 8px and each settings row another 14px, putting row labels 10px right
    of the eyebrow above them. The card now names the difference once.
    """
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-card>.section-heading", "padding-inline"
    ), "every Tools card heading must declare one horizontal inset"
    # `_declarations` drops custom properties, so this has to read the sheet.
    # The point is that the row inset is *derived* from the heading inset: two
    # independent numbers is exactly how they drifted 10px apart before.
    settings_inset = re.search(
        r"#page-tools\s*\.tool-settings\s*\{[^}]*--ui-settings-inset\s*:\s*([^;}]+)",
        SHEETS["appearance-overrides.css"],
    )
    assert settings_inset, "the settings cards must name their row inset, not hard-code it"
    assert "--ui-heading-pad-x" in settings_inset.group(1), (
        "the settings row inset must be derived from the heading inset, found "
        f"{settings_inset.group(1).strip()!r}; a second independent number is what "
        "let row labels sit 10px right of the eyebrow above them"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-card>.section-heading", "padding-inline"
    ), "the heading inset must be declared once for every card"
    inset = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .settings-row", "padding-inline"
    )
    assert inset == ["var(--ui-settings-inset)!important"], (
        "settings rows must take the shared inset rather than a hard-coded "
        f"padding, found {inset!r}"
    )


def test_tool_body_padding_is_not_rewritten_per_breakpoint():
    """The expanded Tool body has one padding at every width.

    Measured defect: styles.css declared `padding:8px` for an open collapsible
    and then `padding:7px` again under `max-width:560px`, so on a phone an
    expanded card sat one pixel tighter than its collapsed siblings.
    """
    for prelude, body, media in _iter_rules(SHEETS["styles.css"]):
        if "#page-tools .tool-collapse.is-open>.tool-body" not in _selectors(prelude):
            continue
        properties = _declarations(body)
        assert "padding" not in properties or media == "none", (
            f"`{prelude}` (media {media}) restates the expanded Tool body "
            "padding; the single 8px declaration is the whole contract and a "
            "second one only re-introduces the one-pixel mismatch"
        )


def test_settings_account_fields_are_labelled_and_share_one_grid():
    """Every account number says what it holds, and the three share one row.

    Measured defect: an account was one row of three bare number boxes (only an
    `aria-label`, no visible label, no unit) followed by a second, differently
    sized "<name> budget" row. At 390px the third box wrapped under the first
    two because each was pinned to 104px inside 336px of content.
    """
    assert 'class="settings-field"' in APP and "<span class=\"settings-field-label\">" in APP, (
        "each account number needs a visible unit label, not only an aria-label"
    )
    assert 'class="settings-account-fields"' in APP, (
        "the three account numbers must live in one named container so the grid "
        "has something to size them from"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .settings-account-fields", "grid-template-columns"
    ) == ["repeat(3,minmax(0,1fr))!important"], (
        "the account fields are a three-column grid; anything else re-creates "
        "the 2-then-1 break the fix removed"
    )
    for prelude, body, _media in _iter_rules(SHEETS["styles.css"]):
        if "#page-tools .settings-input[type=number]" in _selectors(prelude):
            assert False, (
                f"`{prelude}` pins a number field to a fixed width; the grid it "
                "lives in now owns that, and a fixed width cannot shrink to fit"
            )


def test_settings_session_selects_use_the_card_control_contract():
    """The session selects are the same control as every other field.

    Measured defect: `#settingsStartHour` rendered 350x36 at 12px with
    `appearance:auto`, i.e. the OS bevel and the OS chevron, beside 104x32 11px
    inputs in a card whose control height is 32px.
    """
    appearance = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .backtest-controls select", "appearance"
    )
    assert appearance == ["none!important"], (
        f"the session selects must drop the platform widget, found {appearance!r}"
    )
    height = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .backtest-controls select", "height"
    )
    assert height == ["var(--ui-control-h)!important"], (
        f"the session selects must take the card's control height, found {height!r}"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .backtest-controls label::after", "content"
    ), "a native-looking select needs the project's own chevron back"


def test_settings_save_and_reset_are_not_the_same_component():
    """Save and Reset must not render as the same button.

    Measured defect: both carried `class="chip-option"`, so both were 9.5px/600
    on `rgb(241,243,246)` with a 1px grey border and no shadow. A programmatic
    diff over ten computed axes returned no differences at all.
    """
    save = re.findall(r'<button class="([^"]+)"[^>]*data-save-settings>', HTML)
    reset = re.findall(r'<button class="([^"]+)"[^>]*data-reset-settings>', HTML)
    assert save and len(save) == len(reset), (
        "every card that owns data must carry its own Save and Reset: adding an "
        "asset must not mean scrolling to a different card to commit it"
    )
    for key in ("universe", "accounts", "routing"):
        card = _tools_card_html(key)
        assert "data-save-settings" in card and "data-reset-settings" in card, (
            f"the {key} card owns data but has nowhere to commit it"
        )
    for classes in save:
        assert "primary-button" in classes, (
            f"Save is a committing action but renders as {classes!r}"
        )
    for classes in reset:
        assert "secondary-button" in classes, (
            f"Reset renders as {classes!r}, the same component as Save"
        )
    assert save[0] != reset[0], "Save and Reset must not share a class list"
    assert 'id="saveSettingsButton"' not in HTML, (
        "the single Changes card is back; Save belongs in the card it saves"
    )


def test_settings_dirty_state_is_visible_on_the_card():
    """An unsaved edit has to be visible where the Save button is.

    Measured defect: `markSettingsDirty()` only wrote `#settingsStatus`, which
    sat 2,220px below the first settings row in a 2,456px card, and a diff of
    the two buttons found nothing to tell them apart.
    """
    assert 'id="settingsDirtyBadge"' not in HTML and 'id="settingsStatus"' not in HTML, (
        "the dirty state lives on the Save button in each card now; one badge "
        "and one status line in a distant card is exactly what it replaced"
    )
    for key in ("universe", "accounts", "routing"):
        assert "data-settings-status" in _tools_card_html(key), (
            f"the {key} card commits data but cannot say whether Save worked "
            "without the operator leaving the card"
        )
    assert "function paintSettingsDirty()" in APP, (
        "the Save buttons are declared in dashboard.html but nothing in app.js "
        "ever marks them"
    )
    mark = re.search(r"function markSettingsDirty\(\)\{(.*?)\n?\}", APP, re.S)
    assert mark and "paintSettingsDirty()" in mark.group(1), (
        "`markSettingsDirty` does not repaint the badge, so the moment an edit "
        "is made is exactly the moment nothing on screen says so"
    )
    saved = APP.split("state.settingsDirty=false;", 1)
    assert len(saved) == 2 and "paintSettingsDirty()" in saved[1].split("renderSettings()", 1)[0], (
        "a successful save never clears the dirty state before the card "
        "re-renders, so a card with no unsaved changes still reads as dirty"
    )
    # The card the operator pressed Save in has to be the one that answers.
    assert '$$("[data-settings-status]")' in APP, (
        "the status is written to a single element again, so the cards that own "
        "the other Save buttons show nothing when one of them is pressed"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .settings-actions .primary-button.is-dirty",
        "box-shadow",
    ), "the dirty state on Save must be visible, not just a class name"
    for prelude, _body, _media in _iter_rules(SHEETS["appearance-overrides.css"]):
        assert not any(".settings-dirty" in s for s in _selectors(prelude)), (
            f"`{prelude}` still styles the removed Changes badge"
        )


def test_settings_reorder_buttons_have_their_own_geometry_and_disabled_state():
    """`↑` / `↓` are actions, not routing options.

    Measured defect: they carried `chip-option settings-toggle`, so a 3-way
    exclusive choice sat beside two arrows painted identically, and no
    stylesheet had any `.settings-toggle:disabled` rule, so the disabled
    first/last arrow looked enabled.
    """
    assert 'settings-toggle settings-move' in APP, (
        "the reorder buttons must carry `settings-move` so they can be told "
        "apart from the option chips beside them"
    )
    # The rule carries the `html` prefix so it out-reaches the chip step it
    # sits beside; one rule, not a second trio layered on top of the first.
    width = _declarations_for_selector(
        "appearance-overrides.css",
        "html #page-tools .tool-settings .settings-move",
        "width",
    )
    assert width == ["var(--ui-collapse-size)!important"], (
        f"a reorder button is a square icon target, found {width!r}"
    )
    bases = [
        prelude
        for prelude, _body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if "html #page-tools .tool-settings .settings-move" in _selectors(prelude)
    ]
    assert len(bases) == 1, (
        f"the reorder button's geometry is declared {len(bases)} times ({bases!r}); "
        "superseded rules must be folded into the one that wins, not stacked"
    )
    disabled = [
        prelude
        for prelude, _body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if "html #page-tools .tool-settings .settings-move:disabled" in _selectors(prelude)
    ]
    assert disabled, (
        "there is no disabled style for the reorder buttons; the first rule's "
        "up arrow and the last rule's down arrow both look available"
    )


def test_mobile_nav_clearance_is_reserved_once_not_three_times():
    """The Tools page used to end in 244px of empty background.

    Measured defect: foundation.css reserves `--f-mobile-nav-clearance` on
    `body` and again on `main`, and styles.css reserves another `92px` on
    `.app`, so below the last card sat 76 + 76 + 92px of nothing. `.app` is the
    shell that owns the space around the fixed nav.
    """
    for selector in ("#main-content", "body"):
        assert _declarations_in_media(
            "appearance-overrides.css", selector, "padding-bottom", "max-width:900px"
        ) == ["0!important"], (
            f"`{selector}` must hand its mobile nav clearance back to `.app`; "
            "reserving it three times stacks ~244px of dead space under the "
            "last card"
        )
    assert _declarations_for_selector(
        "styles.css", ".app", "padding-bottom"
    ) or "padding-bottom:calc(92px" in SHEETS["styles.css"], (
        "`.app` must keep the clearance that the inner reservations hand back"
    )


def test_settings_rows_do_not_repeat_the_group_they_sit_in():
    """A row label must not restate the group header directly above it.

    Measured defect: the Assets group header and its own empty-state row both
    read "ASSETS", and each routing rule labelled two of its three rows with
    the account name the row above it already carried.
    """
    empty_assets = re.search(r'if\(!model\.assets\.length\)return`([^`]+)`', APP)
    assert empty_assets, "the empty Assets state must still be rendered"
    labels = re.findall(r'<span class="settings-label">([^<]+)</span>', empty_assets.group(1))
    assert labels == ["Added assets"], (
        f"the empty Assets row is labelled {labels!r}; repeating the group "
        "header above it reads as two sections that are both called Assets"
    )
    assert 'class="settings-row settings-rule' in APP, (
        "a routing rule must be one block, not three rows that each repeat the "
        "account name"
    )
    assert 'class="settings-rule-summary"' in APP and 'class="settings-rule-body"' in APP, (
        "a routing rule must state its contract on one line and keep its chip "
        "groups behind a control, or four rules bury the order they are in"
    )
    # Read-only chip geometry, layered: the row is a summary, the groups are
    # behind a control, and the contract has to survive the re-render every
    # edit triggers.
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .settings-rule>.settings-rule-body",
        "display",
    ) == ["none!important"], (
        "a routing row must start collapsed, or the chip wall is back"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .settings-rule.is-open>.settings-rule-body",
        "display",
    ) == ["flex!important"], "an opened routing row must show its chip groups"
    assert "state.expandedRules.add(" in APP and "state.expandedRules.delete(" in APP, (
        "the open row is not remembered in state, so the re-render every edit "
        "triggers collapses the row the operator is working in"
    )
    # The session was two rows: a start/end pair plus a full-width read-out.
    # Three 32px controls fit on one line at every supported width.
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .session-controls",
        "grid-template-columns",
    ) == ["repeat(3,minmax(0,1fr))!important"], (
        "the session must stay on one line; stacking it re-adds the row it gave up"
    )
    for group in ("Strategies", "Assets", "Session"):
        assert f'group("{group}"' in APP, (
            f'the "{group}" chip group has no caption, so the chips have no '
            "visible owner"
        )


def test_removed_runtime_card_render_is_null_guarded():
    """Removing a Tools card must not take the dashboard down with it.

    `loadDashboard()` renders the Diagnostics grid by id. With the card gone the
    lookup returns null, so the unguarded `$("diagnostics").innerHTML=...` would
    throw inside loadDashboard and take every other panel down with it.
    """
    assert '$("diagnostics").innerHTML=' not in APP, (
        "the Diagnostics render is unguarded; the card it filled was removed, "
        "so the lookup returns null and loadDashboard throws"
    )
    assert 'const diagnosticGrid=$("diagnostics");' in APP and "if(diagnosticGrid)" in APP, (
        "the Diagnostics render must read the element once and test it before "
        "writing to it"
    )


def test_neo_hard_shadow_never_reaches_the_modern_style():
    """The Neo ink shadow must be scoped to Neo.

    Measured defect: every member of the Neo interactive-surface list was
    `html[data-style="neo"] ...` / `html.neo-mode ...` except a bare
    `#page-tools .settings-input`, so all twelve settings fields rendered
    `box-shadow: rgba(15,23,42,0.26) 2px 2px 0` in Modern, Light and every
    accent -- the only shadowed element in the card. A later rule re-declared
    the field's border and radius but not the shadow, so the `!important`
    survived it.
    """
    neo_shadow = "2px 2px 0 var(--line-strong)!important"
    shadowed = [
        selector
        for prelude, body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if _declarations(body).get("box-shadow") == neo_shadow
        for selector in _selectors(prelude)
    ]
    leaking = [
        selector
        for selector in shadowed
        if 'data-style="neo"' not in selector and "neo-mode" not in selector
    ]
    assert not leaking, (
        f"the Neo hard shadow is declared for {sorted(set(leaking))}; a bare "
        "selector paints the ink shadow in Modern and Material 3 too"
    )
    assert any(
        'data-style="neo"' in selector and selector.endswith("#page-tools .settings-input")
        for selector in shadowed
    ), (
        "the settings field is no longer enrolled in the Neo surface contract, "
        "so switching style would leave it with a flat border and no shadow"
    )


# ---------------------------------------------------------------------------
# Round 4: the Tools page carried four different heading blocks on one screen.
# ---------------------------------------------------------------------------

TOOLS_CARD_NAMES = (
    ".tool-backtest", ".tool-settings", ".tool-universe",
    ".tool-accounts", ".tool-rules", ".tool-runtime",
)
APPEARANCE_SHEET = "appearance-overrides.css"
# `_iter_rules` keeps the comment that precedes an at-rule in its prelude, so a
# documented `@media` block never looks like one. Comment-free copies let these
# guards see every at-rule wherever it sits; that quirk is what let a
# phone-only heading sneak past the first draft of these tests.
PLAIN = {
    name: re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for name, css in SHEETS.items()
}


def _rules_naming_one_tools_card(css, needle):
    """Rules that scope `needle` to a single Tools card rather than to all."""
    return [
        prelude
        for prelude, _body, _media in _iter_rules(css)
        if needle in prelude
        and ".tool-card" not in prelude
        and ".tools-appearance" not in prelude
        and any(card in prelude for card in TOOLS_CARD_NAMES)
    ]


def _tools_card_html(key):
    """The markup of one Tools card, delimited by its own `</section>`.

    A Tool card contains no nested `<section>`, so this is exact and a control
    that escaped the card cannot still be counted as inside it.
    """
    match = re.search(
        rf'<section class="tool-card [^"]*" data-tool-collapse data-tool-key="{re.escape(key)}".*?</section>',
        HTML,
        re.S,
    )
    assert match, f"the {key} card was not found in dashboard.html"
    return match.group(0)


def test_every_tools_card_heading_is_the_same_block():
    """One heading geometry for all ten Tools cards.

    Measured defect at 390x844, one row per card: appearance 64px, backtest 51,
    universe 57, accounts 57, settings 55, rules 57, runtime 57 -- with a 15px,
    a 16px and a 17px title and both a 10px and an 11px tag on the same page.
    Three separate blocks had each claimed the heading (Appearance, Backtest and
    the settings cards) and, being more specific, they outranked the 17px step
    that `html #page-tools .section-heading h2` already declared.
    """
    owners = [
        (prelude, media, _declarations(body))
        for prelude, body, media in _iter_rules(PLAIN[APPEARANCE_SHEET])
        if "#page-tools .tool-card>.section-heading" in _selectors(prelude)
    ]
    assert owners, "nothing declares the shared Tools heading geometry"

    contract_prelude, contract_media, contract = owners[-1]
    required = ("min-height", "padding-block", "padding-inline", "gap", "align-items", "flex-wrap")
    missing = [prop for prop in required if prop not in contract]
    assert not missing, (
        f"the rule that wins the cascade for the Tools heading (`{contract_prelude}`) "
        f"does not declare {missing}. An incomplete contract can only be completed by "
        "a card-specific rule, and three of those are what produced four different "
        "heading heights on one page."
    )
    assert contract_media == "none", (
        f"the winning heading rule sits inside {contract_media}; the contract must "
        "hold at every width or a card is one size on a phone and another on a desktop"
    )

    claiming = _rules_naming_one_tools_card(PLAIN[APPEARANCE_SHEET], ".section-heading")
    assert not claiming, (
        "a single Tools card claims its own heading geometry again, so it renders a "
        f"different size block from its neighbours: {claiming}"
    )

    titles = _declarations_for_selector(
        APPEARANCE_SHEET, "#page-tools .tool-card>.section-heading h2", "font-size"
    )
    assert titles == ["17px!important"], (
        f"every Tools title must sit on the 17px display step, found {titles!r}"
    )


def test_tools_card_heading_has_no_breakpoint():
    """No breakpoint may restate any Tools card's heading geometry.

    Measured defect: the Appearance, Backtest and settings headings each
    re-declared their padding and a 15px title inside `@media(max-width:560px)`,
    and the shared header block did too with a 50px min-height -- so the same
    card measured one height on a phone and another on a desktop.
    """
    for prelude, body, media in _iter_rules(PLAIN[APPEARANCE_SHEET]):
        if media == "none":
            continue
        for selector in _selectors(prelude):
            if ".section-heading" not in selector:
                continue
            assert ".tool-card" not in selector, (
                f"`{selector}` re-declares the shared heading contract inside "
                f"{media}; the contract must hold at every width"
            )
            assert not any(card in selector for card in TOOLS_CARD_NAMES), (
                f"`{selector}` re-declares one card's heading inside {media}"
            )
        if any(".section-heading" in s for s in _selectors(prelude)):
            assert "font-size:15px" not in body and "font-size:16px" not in body, (
                f"`{prelude}` restores a phone-only Tools title size inside {media}"
            )


def test_tools_card_tags_are_one_size():
    """A tag is content, not geometry: one pill on every card.

    Measured defect: the Markets tag rendered 11px beside the settings card's
    10px, and the Backtest tag was hidden entirely below 560px, so one heading
    showed a pill and the next did not.
    """
    assert _declarations_for_selector(
        APPEARANCE_SHEET, "#page-tools .tool-card>.section-heading .tool-tag", "font-size"
    ) == ["10px!important"], "every Tools tag must take one small-text step"
    claiming = _rules_naming_one_tools_card(PLAIN[APPEARANCE_SHEET], ".tool-tag")
    assert not claiming, f"a single Tools card claims its own tag geometry: {claiming}"
    assert ".tool-backtest .tool-tag{display:none}" not in SHEETS["styles.css"], (
        "styles.css hides the Backtest tag on a phone again, so one heading shows "
        "a pill and its neighbour does not"
    )


def test_appearance_note_is_not_part_of_the_heading():
    """The Appearance panel's note must not be inside its heading.

    Measured defect: the note sat under the title, which alone made the
    Appearance heading 64px against 57px on its neighbours -- the one card whose
    block size was decided by prose. It is a footnote on the card now, and the
    heading is the same eyebrow + title as every other card.

    The Heading is read out of the Appearance card itself: the first
    `<div class="section-heading">` on the page belongs to Home's equity chart,
    so a whole-document search silently checked the wrong element.
    """
    card = re.search(
        r'<section class="tool-card [^"]*tools-appearance[^"]*".*?</section>', HTML, re.S
    )
    assert card, "the Appearance card was not found"
    heading = re.search(r'<div class="section-heading">(.*?)</div></div>', card.group(0), re.S)
    assert heading, "the Appearance card must still have a .section-heading"
    assert "section-note" not in heading.group(1), (
        "a note is inside the Appearance heading again, so that heading is taller "
        "than every other heading on the page"
    )
    assert 'class="section-note section-foot"' in HTML, (
        "the Appearance note must still be rendered, as a footnote on the card"
    )
    assert _declarations_for_selector(
        APPEARANCE_SHEET, "#page-tools .tools-appearance>.section-note", "border-top"
    ), "the footnote needs its separator, or it reads as part of the last row"


def test_bot_settings_is_split_into_one_card_per_concern():
    """Accounts, assets, routing and saving are separate cards.

    The single "Accounts, assets and routing" card held four unrelated editing
    surfaces behind one heading, so the account limits and the routing order --
    which do not affect each other -- shared one heading and one scroll position.
    """
    assert 'class="tool-card tool-settings tool-collapse"' not in HTML, (
        "the monolithic settings card is back; accounts and routing must not "
        "share one heading"
    )
    keys = dict(
        (key, classes)
        for classes, key in re.findall(
            r'<section class="tool-card ([^"]*)"[^>]*data-tool-key="([^"]+)"', HTML
        )
    )
    for key in ("universe", "accounts", "routing"):
        assert key in keys, f"the {key} card is missing"
        assert "tool-settings" in keys[key], (
            f"the {key} card must keep the shared `tool-settings` marker so the "
            "row, chip and inset contracts reach it"
        )
    for key in ("account-limits", "added-assets", "changes", "runtime"):
        assert key not in keys, (
            f"the {key} card is back: it either repeats a card that already "
            "shows that data or holds only a control that belongs beside it"
        )
    for control, key in (
        ("addAccountButton", "accounts"),
        ("settingsAccounts", "accounts"),
        ("accountsGrid", "accounts"),
        ("addAssetButton", "universe"),
        ("settingsAssets", "universe"),
        ("universeGrid", "universe"),
        ("settingsRules", "routing"),
        ("settingsStartHour", "routing"),
    ):
        assert control in _tools_card_html(key), (
            f"`{control}` must live inside the {key} card, beside the data it "
            "acts on, not in a neighbouring section"
        )
    assert 'id="saveSettingsButton"' not in HTML, (
        "Save is in the card that owns the data now, not in a shared Changes card"
    )


def test_tools_cards_own_their_own_height():
    """A Tools card must not be taller than the content inside it.

    Measured defect: `.tool-universe,.tool-accounts,.tool-rules,.tool-runtime`
    took `min-height:100%`, which read as tidy while each of those cards was one
    line of summary. Once Assets and Accounts carried their own editor, the
    shorter card of a grid row was stretched to whatever the card beside it
    measured and rendered ~229px of empty surface inside its border -- the same
    dead space this page was already reported for. `align-items:start` on
    `.tools-layout` keeps the tops aligned, which is what reads as alignment.
    """
    stretched = {".tool-universe", ".tool-accounts", ".tool-rules", ".tool-runtime"}
    for name, sheet in SHEETS.items():
        for prelude, body, _media in _iter_rules(sheet):
            if "min-height:100%" not in body:
                continue
            offenders = [s for s in _selectors(prelude) if s.strip() in stretched]
            assert not offenders, (
                f"`{prelude}` in {name} stretches a Tools card to fill its grid "
                "row again, so the shorter card of the row renders empty surface "
                "inside its own border"
            )


def test_account_limits_are_editable_on_every_account():
    """The editor must not refuse an edit the API accepts.

    Measured defect: `accountRows()` appended `${fixed?" disabled":""}` to all
    three number fields, so every one of the twelve fields on the four shipped
    accounts rendered disabled at `opacity:.62` with `cursor:not-allowed` and the
    operator could not change capital, trade cap or risk per trade. The server
    guards only *deletion* -- `bot_settings.py` raises "Built-in accounts cannot
    be removed" -- while capital, trade cap and risk are range-checked and
    written for every account alike.
    """
    field = re.search(r"const field=\(key,label,min,max,step\)=>(.*?)\n", APP, re.S)
    assert field, "the account field helper was renamed or removed"
    assert "disabled" not in field.group(1), (
        "the limit fields are disabled again, so the dashboard refuses an edit "
        "that bot_settings.py validates and applies"
    )
    assert '${fixed?" disabled":""}' not in APP, (
        "the per-account disabled flag is back on the settings fields"
    )
    # Only deletion is withheld from the shipped books.
    assert 'const remove=fixed?"":' in APP, (
        "the shipped accounts lost their remove guard: the server rejects the "
        "whole document when one of the four is missing"
    )


def test_per_account_performance_is_derived_from_the_trade_ledger():
    """Per-account performance costs no extra request and cannot disagree.

    Measured defect: the Accounts card showed a read-only grid of balances and,
    below it, an editor for the same books, so reading an account and changing
    it were two places and neither said how the account was doing. The grid is
    now that account's performance line, derived from the trade ledger the
    dashboard already receives.
    """
    assert "function accountPerformance(" in APP, (
        "there is no per-account performance helper; the grid is a balance "
        "read-out again"
    )
    helper = APP.split("function accountPerformance(", 1)[1].split("\nfunction ", 1)[0]
    assert "trades" in helper and "winRate" in helper, (
        "the helper must derive closed trades and a win rate from the ledger"
    )
    grid = re.search(r'\$\("accountsGrid"\)\.innerHTML=(.*?)\.join\(""\);', APP, re.S)
    assert grid, "the account performance grid is no longer rendered"
    body = grid.group(1)
    assert "accountPerformance(" in body, (
        "the grid no longer asks the helper, so it shows balances and no "
        "performance"
    )
    for fact in ("remaining_planned_risk", "closed", "account-pnl"):
        assert fact in body, (
            f"the per-account line dropped {fact!r}; it has to carry the live "
            "state and the result in one compact row"
        )
    # The result must be legible on both signs without a colour-only cue.
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .account-grid>article strong.account-pnl.positive",
        "color",
    ) == ["var(--positive)!important"], (
        "a profit is signalled by colour alone again"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .account-grid>article strong.account-pnl.negative",
        "color",
    ) == ["var(--negative)!important"]
    assert 'p.pnl>=0?"+":"−"' in APP, (
        "the P/L is printed without a sign, so a loss reads as a gain"
    )


def test_session_row_is_one_line_including_the_live_readout():
    """`grid-template-columns` alone does not prove the row is one line.

    Measured defect: the three-column rule was present and measured correct,
    and a guard that only read `grid-template-columns` passed -- while
    `#page-tools .tool-settings .settings-session-live{grid-column:1/-1}` still
    pushed "Right now" onto a row of its own, so the session rendered as a
    start/end pair plus a full-width third control. The span has to be asserted
    as well, or the half of the fix that did not work looks like a pass.
    """
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .settings-session-live",
        "grid-column",
    ) == ["auto!important"], (
        "the live read-out spans the grid again, which puts the session back on "
        "two rows while the column rule still reports a pass"
    )


def test_reorder_controls_look_like_controls():
    """`↑` / `↓` must read as the controls that decide the routing order.

    Measured defect: 32px of transparent background on `--muted` at 12px, so
    the pair rendered as two grey specks with nothing saying what they did. A
    reader could not tell they were buttons, let alone which end of the order
    they moved a rule to. They now carry the chip surface, a 13px glyph, a
    `title`/`aria-label` naming the action, and a "Move" caption in front of
    the pair.
    """
    # The chip step is declared on `html #page-tools .tool-settings
    # .chip-option`; an unprefixed rule loses to it and the glyph stays 9.5px,
    # so the one rule carries the prefix and both declarations.
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "html #page-tools .tool-settings .settings-move",
        "background",
    ) == ["var(--surface)!important"], (
        "the reorder buttons are transparent again, so they read as decoration"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "html #page-tools .tool-settings .settings-move",
        "font-size",
    ) == ["13px!important"], (
        "the reorder glyph is back on the 9.5px chip-label step, which is too "
        "small to read as an arrow"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css",
        "#page-tools .tool-settings .settings-rule-move::before",
        "content",
        # `_declarations_for_selector` lowercases the value it returns.
    ) == ['"move"!important'], (
        "the pair has no caption, so nothing on screen says what it does"
    )
    assert 'title="${escapeHtml(label)}"' in APP, (
        "the reorder buttons have no hover title, so the action is still unnamed"
    )
    assert '"Move "+rule.account+" up"' in APP and '"Move "+rule.account+" down"' in APP, (
        "the reorder names lost their direction, so up and down read the same"
    )


def test_typing_a_limit_does_not_rebuild_the_row():
    """A re-render mid-typing drops focus, which makes a field uneditable.

    Measured defect: both input handlers ended in `renderSettings()`, which
    replaces the row's `innerHTML`. Typing one character into capital measured
    `sameNodeAfter: false` and `activeElement === document.body`, so the limit
    fields accepted exactly one character per click -- enabled, and still
    impossible to edit. This is the half of the complaint that removing
    `disabled` did not fix.
    """
    for handler in ("settingsAccounts", "settingsAssets"):
        split = APP.split(f'bindEvent("{handler}","input",', 1)
        assert len(split) == 2, f'`{handler}` has no input handler left'
        body = split[1].split("\n});", 1)[0]
        # Comments stripped first: the handler explains in prose which function
        # it must not call, and a bare substring check matched that prose.
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        body = re.sub(r"(?m)^\s*//.*$", "", body)
        assert "renderSettings()" not in body, (
            f'`{handler}` rebuilds its rows while the operator types, so focus '
            "falls to <body> after one keystroke"
        )
        assert "markSettingsDirty()" in body, (
            f'`{handler}` must still mark the edit unsaved'
        )
    # The derived line has one definition, shared by the first render and the
    # in-place update, so the two cannot drift apart.
    assert "function accountSummary(" in APP, (
        "the derived account line has no shared builder again"
    )
    assert "hint.textContent=accountSummary(account)" in APP, (
        "the in-place update and the first render no longer agree on the "
        "derived account line"
    )


def test_adding_an_asset_can_actually_be_saved():
    """The Assets editor must be able to build a document the API accepts.

    Measured defect: `bot_settings.py::_normalize_assets` requires `symbol`
    ("Asset N needs a symbol") and rejects an asset whose strategy list is empty
    ("strategies must select at least one name, or null for all"), while the
    editor offered no symbol field at all and seeded `strategies:[]`. Every
    "+ New asset" therefore posted `symbol:""` with nothing ticked and was
    refused -- verified in the browser as `error | IDEA strategies must select
    at least one name` before the fix, and `success | Settings saved` after.
    """
    assert 'text("symbol","Symbol")' in APP, (
        "the asset row has no symbol field, which the server requires"
    )
    payload = APP.split("function settingsPayload()", 1)[1].split("\nfunction ", 1)[0]
    assert "toUpperCase()" in payload and "trim()" in payload, (
        "the payload sends the symbol untrimmed, so it cannot match what "
        "_normalize_assets stores"
    )
    add = APP.split("function addAsset()", 1)[1].split("\nfunction ", 1)[0]
    assert "strategies:null" in add, (
        "a new asset is seeded ticking nothing, which the server refuses"
    )
    click = APP.split('bindEvent("settingsAssets","click",', 1)[1].split("\n});", 1)[0]
    assert "must ride at least one strategy" in click, (
        "the chip handler no longer refuses to empty an asset's strategy list, "
        "so the UI can build a document the server rejects"
    )
    assert "??[...every]" in click, (
        "the chip handler does not read null as every strategy, so untick/retick "
        "on a default row silently loses the others"
    )
    assert "asset.strategies||model.strategies" in APP, (
        "the asset chips read `asset.strategies` directly, so a default (null) "
        "row throws while rendering"
    )


# ---------------------------------------------------------------------------
# UI/UX standard re-audit (2026-10-04) — state, token and lifecycle contracts.
# The defect in every case below was one shared component doing two jobs, so
# each guard asserts the replacement AND the absence of the superseded pattern.
# ---------------------------------------------------------------------------

def test_loading_is_a_skeleton_not_a_sentence_in_an_empty_tile():
    """A loading list must show the shape of what is coming.

    Measured defect: six containers shipped
    ``<div class="empty-state">Loading signals…</div>``, so before the first
    poll a list that was *loading* and a list that was genuinely *empty*
    rendered the same component with different words in it.
    """
    for phrase in (
        "Loading signals…",
        "Loading history…",
        "Loading open trades…",
        "Loading scan history…",
        "Loading saved calendar…",
    ):
        assert f'class="empty-state">{phrase}' not in HTML, (
            f"{phrase!r} is still bare text inside an empty-state tile, so "
            "loading and empty remain the same component"
        )
    assert HTML.count('class="loading-state" role="status"') >= 6, (
        "every loading list must use .loading-state and declare role=status"
    )
    # Row-shaped bars, not one bar: the placeholder has to read as a list.
    assert HTML.count('class="skeleton skeleton-row"') >= 12, (
        "each loading list needs row-shaped skeletons to match the rows coming"
    )
    # The bars are decoration; the meaning is carried once, accessibly.
    assert HTML.count('<span class="sr-only">Loading') >= 6, (
        "each loading list needs one accessible loading label"
    )


def test_skeleton_respects_reduced_motion_and_matches_row_height():
    """The shimmer must stop for reduced-motion users and use surface tokens."""
    reduce_rules = [
        body
        for prelude, body, media in _iter_rules(SHEETS["styles.css"])
        if "prefers-reduced-motion" in media and ".skeleton" in _selectors(prelude)
    ]
    assert reduce_rules, "the skeleton shimmer is not disabled under reduced motion"
    assert "animation:none" in reduce_rules[0]
    assert "background:var(--surface-2)" in SHEETS["styles.css"], (
        "the skeleton must fill from a surface token, not a hex colour"
    )
    assert not re.search(r"\.skeleton\s*\{[^}]*#[0-9a-fA-F]", SHEETS["styles.css"]), (
        "the skeleton hardcodes a colour instead of using a token"
    )
    # Dimension-matched, not eyeballed: 64px is a real row height in this app
    # (.calendar-item measures 64px; .signal-card measures 70px), so a
    # placeholder bar is the size of something that actually exists here.
    assert re.findall(r"\.skeleton-row\{height:(\d+)px\}", SHEETS["styles.css"]) == ["64"], (
        "the skeleton row must match a measured row height (64px)"
    )


def test_reorder_control_defines_a_pressed_state():
    """The five-state contract: this control was the only one with no `:active`.

    Measured defect: `.settings-move` defined base, hover and disabled but no
    pressed rule at all, so pressing an arrow gave no feedback whatsoever.
    """
    sheet = SHEETS["appearance-overrides.css"]
    for state in ("", ":hover:not(:disabled)", ":active:not(:disabled)", ":disabled"):
        selector = f"html #page-tools .tool-settings .settings-move{state}"
        found = [p for p, _b, _m in _iter_rules(sheet) if selector in _selectors(p)]
        assert found, f"the reorder control defines no rule for {selector!r}"
    pressed = [
        body
        for prelude, body, _media in _iter_rules(sheet)
        if "html #page-tools .tool-settings .settings-move:active:not(:disabled)"
        in _selectors(prelude)
    ]
    assert "background:var(--accent-soft)!important" in pressed[0], (
        "the pressed state must actually change the surface"
    )
    assert "transform" not in pressed[0], (
        "the press must not move a control whose geometry is pinned (the hover "
        "rule sets transform:none, because only a chevron may move here)"
    )


def test_connection_error_offers_a_retry_and_can_still_hide():
    """An error banner is an error contract: it needs a retry trigger.

    Measured defect: the banner only ever received `textContent`, so an
    operator whose dashboard went offline had no way to retry without a
    full page reload.
    """
    assert 'class="connection-banner"' in HTML and 'role="alert"' in HTML
    assert "data-retry-dashboard" in APP, "the error banner has no retry control"
    # The banner is re-rendered after load, so the handler must be delegated:
    # a one-time binding would never see the button.
    assert 'closest("[data-refresh-dashboard],[data-retry-dashboard]")' in APP, (
        "the retry button is rendered after hydration, so it needs delegation"
    )
    assert _declarations_for_selector(
        "styles.css", ".connection-banner[hidden]", "display"
    ) == ["none"], (
        "`display:flex` defeats the `hidden` attribute, so the banner must "
        "re-assert display:none or it shows an empty red bar on every healthy load"
    )


def test_empty_state_carries_an_action_and_it_is_wired():
    """An empty or error tile needs a way forward, not only an explanation."""
    assert re.search(r"function empty\([^)]*refresh", APP), (
        "empty() offers no action slot"
    )
    assert APP.count("data-refresh-dashboard") >= 2, (
        "empty() must render the refresh control it advertises"
    )
    opted_in = re.findall(
        r'empty\("(?:No signals yet|No completed trades|History unavailable|'
        r'Open positions unavailable|Scan history unavailable)"[^)]*,true\)',
        APP,
    )
    assert len(opted_in) >= 5, (
        f"only {len(opted_in)} call sites opt into the empty-state action; an "
        "unused slot is dead code"
    )
