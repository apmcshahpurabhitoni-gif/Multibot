/* Notification channels: the Tools card that adds a delivery target.
 *
 * Kept out of app.js on purpose. app.js owns one atomic settings document
 * (accounts, assets, routing) that has to be written whole through a validator
 * that knows nothing about channels; a channel edit is an independent document
 * with its own endpoint. This file reuses the shared settings markup classes
 * plus app.js's escapeHtml/readJsonResponse helpers, so it adds no CSS.
 *
 * Nothing here ever sees a stored webhook address or secret: the server redacts
 * both and a blank field means "keep what is stored".
 */
(function () {
  const EVENT_LABELS = {
    SIGNAL: "New BUY / SELL signal",
    TRADE_CLOSED: "Trade closed (P&L)",
    REMINDER: "Signal reminder",
    STALE: "Stale signal warning",
    SCAN: "Scan complete",
    ERROR: "Scan error",
    SUMMARY: "Daily / weekly summary",
  };
  const TYPE_LABELS = { telegram: "Telegram", discord: "Discord", slack: "Slack", webhook: "Webhook" };
  const model = { channels: [], options: { types: [], events: [], telegram_configured: false } };
  let dirty = false;
  let loading = false;

  const node = (id) => document.getElementById(id);
  const channelsHost = () => node("notificationChannels");

  function setStatus(text, kind) {
    const message = kind === "info" ? "" : " " + kind;
    $$("[data-notifications-status]").forEach((el) => {
      el.className = "settings-actions-status" + message;
      el.textContent = text;
    });
    const region = node("dashboardAnnouncer");
    if (region) region.textContent = "Notifications: " + text;
  }

  function setDirty(value) {
    dirty = value;
    $$("[data-notifications-save]").forEach((button) => button.classList.toggle("is-dirty", dirty));
  }

  function markDirty() {
    setDirty(true);
    setStatus("Unsaved changes", "info");
  }

  function channelById(id) {
    return model.channels.find((c) => c.id === id) || null;
  }

  function nextId(type) {
    const used = new Set(model.channels.map((c) => c.id));
    const base = type === "webhook" ? "webhook" : type;
    let index = 1;
    while (used.has(base + "_" + index)) index += 1;
    return base + "_" + index;
  }

  function addChannel() {
    const type = "webhook";
    model.channels.push({      id: nextId(type), type, label: TYPE_LABELS[type], target: "", secret: "",
      enabled: true, events: model.options.events.slice(), has_target: false, has_secret: false,
    });
    markDirty();
    render();
  }

  function removeChannel(id) {
    model.channels = model.channels.filter((c) => c.id !== id);
    markDirty();
    render();
  }

  function setField(id, field, value) {
    const channel = channelById(id);
    if (!channel) return;
    channel[field] = value;
    if (field === "type") {
      // A channel cannot keep a Telegram chat id after becoming a webhook, or an
      // address the server would reject; the stored secret goes with the old
      // transport too.
      channel.secret = "";
      channel.has_secret = false;
      channel.has_target = false;
      if (!channel.label || channel.label === "Telegram" || Object.values(TYPE_LABELS).includes(channel.label)) {
        channel.label = TYPE_LABELS[value] || value;
      }
      render();
    }
    markDirty();
  }

  function toggleEvent(id, event, on) {
    const channel = channelById(id);
    if (!channel) return true;
    if (on) {
      if (!channel.events.includes(event)) channel.events.push(event);
    } else if (channel.events.length <= 1) {
      // The server refuses a channel that subscribes to nothing, so refuse it
      // here. The caller puts the checkbox back instead of a full redraw, which
      // would drop focus out of the list the operator is working in.
      setStatus("A channel must keep at least one event.", "error");
      return false;
    } else {
      channel.events = channel.events.filter((e) => e !== event);
    }
    markDirty();
    return true;
  }

  function options(values, selected, label) {
    return values.map((value) => `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(label(value))}</option>`).join("");
  }

  function channelRow(channel, index) {
    const webhook = channel.type !== "telegram";
    const base = escapeHtml(channel.label || channel.id);
    const typeLabel = escapeHtml(TYPE_LABELS[channel.type] || channel.type);
    const targetPlaceholder = channel.has_target && !channel.target
      ? "•••• stored · type to replace"
      : (webhook ? "https://…" : "Telegram chat id");
    // The environment default is one fact -- where chat is delivered -- so it
    // edits only the address; its label and transport belong to the env config
    // and it cannot be removed here, only replaced by saving your own channels.
    const fields = channel.default
      ? `<label class="settings-field"><span class="settings-field-label">Chat id</span><input class="settings-input" type="text" value="" placeholder="${channel.has_target ? "•••• stored · type to replace" : "not configured"}" aria-label="${base} chat id" autocomplete="off" spellcheck="false" data-notify-id="${escapeHtml(channel.id)}" data-notify-field="target"></label>`
      : `<label class="settings-field"><span class="settings-field-label">Label</span><input class="settings-input" type="text" value="${escapeHtml(channel.label || "")}" aria-label="${base} label" data-notify-id="${escapeHtml(channel.id)}" data-notify-field="label"></label>
        <label class="settings-field"><span class="settings-field-label">Type</span><select class="settings-input" aria-label="${base} type" data-notify-id="${escapeHtml(channel.id)}" data-notify-field="type">${options(model.options.types || [], channel.type, (t) => TYPE_LABELS[t] || t)}</select></label>
        <label class="settings-field"><span class="settings-field-label">${channel.type === "telegram" ? "Chat id" : "Webhook URL"}</span><input class="settings-input" type="text" value="${escapeHtml(channel.target || "")}" aria-label="${base} ${channel.type === "telegram" ? "chat id" : "webhook URL"}" placeholder="${escapeHtml(targetPlaceholder)}" autocomplete="off" spellcheck="false" data-notify-id="${escapeHtml(channel.id)}" data-notify-field="target"></label>${secretField(channel, webhook, base)}`;
    const events = (model.options.events || []).map((event) => {
      const on = channel.events.includes(event);
      return `<button class="chip-option settings-toggle" type="button" aria-pressed="${on}" data-notify-id="${escapeHtml(channel.id)}" data-notify-event="${escapeHtml(event)}">${escapeHtml(EVENT_LABELS[event] || event)}</button>`;
    }).join("");
    return `<div class="settings-row settings-account${channel.default ? " is-default" : ""}">
      <div class="settings-account-head">
        <span class="settings-label" title="${escapeHtml(channel.id)}">${base}<span class="settings-type-chip">${typeLabel}</span></span>
        <span class="settings-inline">
          <button class="chip-option settings-toggle" type="button" aria-pressed="${channel.enabled ? "true" : "false"}" data-notify-id="${escapeHtml(channel.id)}" data-notify-toggle="enabled">Enabled</button>
          ${channel.default
            ? `<span class="settings-default-chip" title="Comes from the environment. Saving your own channels replaces it; Telegram keeps delivering from the environment while the token and chat id are configured.">Default</span>`
            : `<button class="secondary-button" type="button" data-notify-remove="${index}" aria-label="Remove ${base}">Remove</button>`}
        </span>
      </div>
      <div class="settings-account-fields">${fields}</div>
      <div class="settings-inline settings-notify-events">${events}</div>
    </div>`;
  }

  function secretField(channel, webhook, base) {
    if (!webhook) return "";
    return `<label class="settings-field"><span class="settings-field-label">Auth secret</span><input class="settings-input" type="password" value="" placeholder="${channel.has_secret ? "•••• stored · type to replace" : "optional bearer token"}" aria-label="${base} auth secret" autocomplete="new-password" data-notify-id="${escapeHtml(channel.id)}" data-notify-field="secret"></label>`;
  }

  function render() {
    const host = channelsHost();
    if (!host) return;
    if (!model.channels.length) {
      host.innerHTML = `<p class="section-note">No channel is saved. Telegram still delivers if the bot token and chat id are configured in the environment.</p>`;
    } else {
      host.innerHTML = model.channels.map(channelRow).join("");
    }
    const tag = node("notificationsTag");
    if (tag) {
      const enabled = model.channels.filter((c) => c.enabled).length;
      tag.textContent = model.channels.length ? `${enabled}/${model.channels.length} enabled` : "Telegram only";
    }
    const alerts = node("browserAlertsButton");
    if (alerts && "Notification" in window) {
      const granted = Notification.permission === "granted";
      alerts.textContent = granted ? "Browser alerts on" : "Enable browser alerts";
      alerts.disabled = granted;
    }
  }

  function payload() {
    return {
      channels: model.channels.map((c) => ({
        id: c.id, type: c.type, label: c.label, target: c.target, secret: c.secret,
        enabled: !!c.enabled, events: c.events.slice(),
      })),
    };
  }

  async function post(body) {
    $$("[data-notifications-save],[data-notifications-reset]").forEach((el) => { el.disabled = true; });
    setStatus("Saving to the server…", "loading");
    try {
      const response = await fetch("/api/notifications", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), cache: "no-store",
      });
      const result = await readJsonResponse(response, "Notification API");
      if (result.ok === false) throw new Error(result.error || "Notification change failed");
      apply(result);
      setDirty(false);
      setStatus(result.message || "Notification channels saved.", "success");
    } catch (error) {
      // A refused edit leaves the stored channels untouched, so keep the edits
      // on screen for the operator to correct.
      setStatus(error.message, "error");
    } finally {
      $$("[data-notifications-save],[data-notifications-reset]").forEach((el) => { el.disabled = false; });
    }
  }

  async function load() {
    if (loading || dirty) return;
    loading = true;
    try {
      const response = await fetch("/api/notifications", { cache: "no-store" });
      apply(await readJsonResponse(response, "Notification API"));
      setStatus(model.options.telegram_configured ? "Saved · Telegram token present" : "Saved · Telegram token not set", "info");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      loading = false;
    }
  }

  function apply(payload) {
    if (Array.isArray(payload.channels)) model.channels = payload.channels;
    if (payload.options) model.options = Object.assign(model.options, payload.options);
    render();
  }

  async function enableBrowserAlerts() {
    if (!("Notification" in window)) {
      setStatus("This browser does not support notifications.", "error");
      return;
    }
    try {
      await Notification.requestPermission();
    } catch (error) {
      setStatus(String(error && error.message || error), "error");
      return;
    }
    render();
    setStatus(Notification.permission === "granted" ? "Browser alerts enabled on this device." : "Browser alerts were not allowed.", "info");
  }

  function bind() {
    const card = node("page-tools");
    if (!card) return;
    card.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const remove = target.closest("[data-notify-remove]");
      if (remove) { removeChannel(Number(remove.dataset.notifyRemove)); return; }
      const subscription = target.closest("[data-notify-event]");
      if (subscription) {
        const id = subscription.dataset.notifyId, name = subscription.dataset.notifyEvent;
        const channel = channelById(id);
        // Flipped in place rather than by redrawing the card, so focus and scroll
        // stay where the operator is working.
        if (channel && !toggleEvent(id, name, !channel.events.includes(name))) {
          // The server refuses a channel that subscribes to nothing, so the last
          // toggle simply does not turn off.
          return;
        }
        subscription.setAttribute("aria-pressed", channel && channel.events.includes(name) ? "true" : "false");
        return;
      }
      const toggle = target.closest("[data-notify-toggle]");
      if (toggle) {
        const on = toggle.getAttribute("aria-pressed") !== "true";
        setField(toggle.dataset.notifyId, "enabled", on);
        toggle.setAttribute("aria-pressed", on ? "true" : "false");
        return;
      }
      if (target.closest("#addNotificationButton")) { addChannel(); return; }
      if (target.closest("[data-notifications-save]")) { post(payload()); return; }
      if (target.closest("[data-notifications-reset]")) { post({ action: "reset" }); return; }
      if (target.closest("#browserAlertsButton")) enableBrowserAlerts();
    });
    card.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLSelectElement)) return;
      const field = target.dataset.notifyField;
      // `type` redraws the row, so it is applied once, on change, rather than on
      // every keystroke of the input event.
      if (!field || field === "type") return;
      setField(target.dataset.notifyId, field, target.value);
    });
    card.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) return;
      if (target.dataset.notifyField === "type") setField(target.dataset.notifyId, "type", target.value);
    });
  }

  function boot() {
    if (!channelsHost()) return;
    bind();
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
