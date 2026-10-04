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
    tag = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings>.section-heading>.tool-tag", "font-size"
    )
    assert tag == ["10px!important"], (
        "the settings session tag must take the same small step the Backtest tag "
        f"uses, found {tag!r}; at 11px it is 112px wide and starves the title"
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
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings", "--ui-settings-inset"
    ) is not None
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
    save = re.search(r'id="saveSettingsButton" class="([^"]+)"', HTML)
    reset = re.search(r'id="resetSettingsButton" class="([^"]+)"', HTML)
    assert save and reset, "the Changes row must still carry both actions"
    assert "primary-button" in save.group(1), (
        f"Save is the card's one committing action but renders as {save.group(1)!r}"
    )
    assert "secondary-button" in reset.group(1), (
        f"Reset renders as {reset.group(1)!r}, the same component as Save"
    )
    assert save.group(1) != reset.group(1), "Save and Reset must not share a class list"


def test_settings_dirty_state_is_visible_on_the_card():
    """An unsaved edit has to be visible where the Save button is.

    Measured defect: `markSettingsDirty()` only wrote `#settingsStatus`, which
    sat 2,220px below the first settings row in a 2,456px card, and a diff of
    the two buttons found nothing to tell them apart.
    """
    assert 'id="settingsDirtyBadge"' in HTML, (
        "the Changes row must carry a badge so an unsaved edit is visible "
        "without scrolling to the bottom of a 2,000px card"
    )
    assert "function paintSettingsDirty()" in APP, (
        "the badge is declared in dashboard.html but nothing in app.js ever "
        "shows or hides it"
    )
    mark = re.search(r"function markSettingsDirty\(\)\{(.*?)\n?\}", APP, re.S)
    assert mark and "paintSettingsDirty()" in mark.group(1), (
        "`markSettingsDirty` does not repaint the badge, so the moment an edit "
        "is made is exactly the moment nothing on screen says so"
    )
    saved = APP.split("state.settingsDirty=false;", 1)
    assert len(saved) == 2 and "paintSettingsDirty()" in saved[1].split("renderSettings()", 1)[0], (
        "a successful save never clears the badge before the card re-renders, "
        "so a card with no unsaved changes still reads as dirty"
    )
    assert _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .settings-dirty[hidden]", "display"
    ) == ["none!important"], (
        "the badge is laid out with `display:inline-flex`, which beats the "
        "`hidden` attribute unless it is re-asserted"
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
    width = _declarations_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .settings-move", "width"
    )
    assert width == ["var(--ui-collapse-size)!important"], (
        f"a reorder button is a square icon target, found {width!r}"
    )
    disabled = [
        prelude
        for prelude, _body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if "#page-tools .tool-settings .settings-move:disabled" in _selectors(prelude)
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
    assert "class=\"settings-row settings-rule\"" in APP, (
        "a routing rule must be one block, not three rows that each repeat the "
        "account name"
    )
    for group in ("Strategies", "Assets", "Session"):
        assert f'group("{group}"' in APP, (
            f'the "{group}" chip group has no caption, so the chips have no '
            "visible owner"
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
