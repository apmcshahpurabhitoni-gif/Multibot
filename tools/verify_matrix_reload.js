// Verify one appearance combination that arrived through a real
// localStorage + reload -- the only path that proves `initAppearance()` agrees
// with the state the sweep switched through the UI.
//
// Run after: playwright-cli eval "<set localStorage; location.reload()>"
(async () => {
  const out = {};
  out.viewport = `${window.innerWidth}x${window.innerHeight}`;
  out.dataset = { ...document.documentElement.dataset };
  out.classes = document.documentElement.className;
  out.localStorage = {
    style: localStorage.getItem("mavis-style"),
    accent: localStorage.getItem("mavis-accent"),
    theme: localStorage.getItem("mavis-theme"),
  };
  out.accentToken = getComputedStyle(document.documentElement)
    .getPropertyValue("--accent").trim();
  const pressed = (selector) =>
    [...document.querySelectorAll(selector)]
      .filter((b) => b.getAttribute("aria-pressed") === "true")
      .map((b) => b.textContent.trim());
  out.pressed = {
    style: pressed("[data-style-choice]"),
    accent: pressed("[data-accent-choice]"),
    theme: pressed("[data-theme-choice]"),
  };

  document
    .querySelectorAll("[data-tool-collapse]")
    .forEach((card) => {
      if (!card.classList.contains("is-open")) card.querySelector("[data-tool-toggle]").click();
    });

  const problems = [];
  for (const page of ["tools", "calendar"]) {
    setPage(page);
    void document.body.offsetHeight;
    if (document.documentElement.scrollWidth > window.innerWidth) {
      problems.push(`${page}: horizontal overflow ${document.documentElement.scrollWidth}`);
    }
    const h1 = [...document.querySelectorAll("h1")].filter((e) => e.offsetParent !== null);
    if (h1.length !== 1) problems.push(`${page}: ${h1.length} visible h1`);
  }
  out.problems = problems;

  setPage("tools");
  const status = document.querySelector(".settings-actions-status");
  const row = status ? status.closest(".settings-actions").getBoundingClientRect() : null;
  const save = document.querySelector("[data-save-settings]");
  out.tools = {
    statusText: status ? status.textContent : null,
    statusLines: status ? Math.round(status.getBoundingClientRect().height) : null,
    rowHeight: row ? Math.round(row.height) : null,
    saveGapFromRight: row && save ? Math.round(row.right - save.getBoundingClientRect().right) : null,
    accountNames: [...document.querySelectorAll("#accountsGrid>article>b")].map((e) => e.textContent),
    routingNames: [...document.querySelectorAll("#settingsRules .settings-rule .settings-label")].map((e) => e.textContent),
    moneyAdornment: [...document.querySelectorAll("#settingsAccounts .settings-field")].map(
      (f) => getComputedStyle(f, "::before").content,
    ),
  };

  setPage("calendar");
  // The calendar is the one page that fetches on entry, so wait for its rows
  // rather than measuring the placeholder.
  for (let i = 0; i < 40 && !document.querySelector(".calendar-item"); i++) {
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  void document.body.offsetHeight;
  const item = document.querySelector(".calendar-item");
  if (item) {
    const title = item.querySelector(".calendar-title").getBoundingClientRect();
    const button = item.querySelector(".expand-button").getBoundingClientRect();
    out.calendar = {
      chevronToTitleCentre: Math.round(
        button.y + button.height / 2 - (title.y + title.height / 2),
      ),
      chevronSize: [Math.round(button.width), Math.round(button.height)],
      impactPill: getComputedStyle(item.querySelector(".impact-pill")).display,
      titleLeft: Math.round(title.x),
    };
  } else {
    out.calendar = "no items yet";
  }
  return JSON.stringify(out, null, 1);
})()