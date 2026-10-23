// Nine Lives sidebar panel. Plain web component without build step or dependencies;
// it talks to the integration through the nine_lives/* WebSocket commands.

const STRINGS = {
  en: {
    intro:
      "Replace a device with another one. The new entities take over the entity IDs, " +
      "settings and history of the old ones, so automations and dashboards keep working.",
    oldDevice: "Old device",
    newDevice: "New device",
    choose: "Choose a device…",
    search: "Filter devices",
    next: "Pair entities",
    pairs: "Entity pairs",
    pairsHint: "Choose which new entity replaces each old one. Skipped entities stay with the old device.",
    skip: "— skip —",
    unmatchedNew: "New entities without a partner",
    preview: "Preview",
    back: "Back",
    previewTitle: "What will change",
    renames: "Entity IDs taken over",
    deviceChanges: "Devices",
    deviceArea: "The new device gets the area and labels of the old one.",
    deviceDisable: "The old device is disabled.",
    refs: "Device references rewritten",
    noRefs: "No automation, script, scene or dashboard refers to the old device.",
    reviews: "Please check afterwards",
    blocked: "Not changed",
    manual: "Please adjust by hand",
    reason_yaml_file: "refers to the old device",
    reason_yaml_dashboard: "YAML dashboard, refers to the old device",
    reason_yaml_tags: "uses YAML tags such as !secret or !include",
    tidy: "New ID",
    tidyHint: "the old ID is not used anywhere",
    apply: "Swap devices",
    confirm: "Swap the devices now? A backup is kept and the swap can be undone.",
    done: "Done. The new device now uses the old entity IDs.",
    removeHint: "Once everything works, remove the old device from its integration.",
    again: "Swap another device",
    history: "Completed swaps",
    noHistory: "No swaps yet.",
    dEntities: "Entities",
    dChanges: "References rewritten",
    dReviews: "Flagged for review",
    dReports: "Left for manual editing",
    dCorrections: "Meter corrections",
    dNotes: "Notes on undo",
    newIdMark: "new ID",
    previously: "was",
    duringUndo: "on undo",
    status_pending: "pending",
    status_applied: "applied",
    status_failed: "not possible",
    undoneAt: "undone",
    oldRemoved: "old device removed, cannot be undone",
    nothingElse: "No device references had to be rewritten.",
    undo: "Undo",
    undoConfirm: "Undo this swap?",
    undone: "Swap undone.",
    error: "Error",
    entities: "Entities",
    pending: "Meter corrections in progress",
    isNew: "new",
    since: "since",
    today: "today",
    yesterday: "yesterday",
    unavailable: "unavailable",
    swappedHint: "The device chosen as old was added after the new one. Mixed up?",
    swapSides: "Swap old and new",
    identify: "Identify",
    identifyHint: "Makes the device blink or beep so you can find it.",
    pendingHint: "applied after the recorder's next 5-minute run, around",
  },
  de: {
    intro:
      "Ein Gerät durch ein anderes ersetzen. Die neuen Entitäten übernehmen Entity-IDs, " +
      "Einstellungen und Verlauf der alten, Automationen und Dashboards laufen weiter.",
    oldDevice: "Altes Gerät",
    newDevice: "Neues Gerät",
    choose: "Gerät auswählen …",
    search: "Geräte filtern",
    next: "Entitäten zuordnen",
    pairs: "Zuordnung",
    pairsHint: "Wähle, welche neue Entität jede alte ersetzt. Übersprungene bleiben beim alten Gerät.",
    skip: "— überspringen —",
    unmatchedNew: "Neue Entitäten ohne Partner",
    preview: "Vorschau",
    back: "Zurück",
    previewTitle: "Was sich ändert",
    renames: "Übernommene Entity-IDs",
    deviceChanges: "Geräte",
    deviceArea: "Das neue Gerät bekommt Bereich und Labels des alten.",
    deviceDisable: "Das alte Gerät wird deaktiviert.",
    refs: "Umgeschriebene Geräte-Verweise",
    noRefs: "Keine Automation, kein Skript, keine Szene und kein Dashboard verweist auf das alte Gerät.",
    reviews: "Bitte danach prüfen",
    blocked: "Nicht geändert",
    manual: "Bitte von Hand anpassen",
    reason_yaml_file: "verweist auf das alte Gerät",
    reason_yaml_dashboard: "YAML-Dashboard, verweist auf das alte Gerät",
    reason_yaml_tags: "nutzt YAML-Tags wie !secret oder !include",
    tidy: "Neue ID",
    tidyHint: "die alte ID wird nirgends verwendet",
    apply: "Geräte tauschen",
    confirm: "Geräte jetzt tauschen? Es wird eine Sicherung angelegt, der Tausch lässt sich rückgängig machen.",
    done: "Fertig. Das neue Gerät nutzt jetzt die alten Entity-IDs.",
    removeHint: "Wenn alles läuft, entferne das alte Gerät aus seiner Integration.",
    again: "Weiteres Gerät tauschen",
    history: "Durchgeführte Gerätetausche",
    noHistory: "Noch keine Gerätetausche.",
    dEntities: "Entitäten",
    dChanges: "Umgeschriebene Verweise",
    dReviews: "Zur Prüfung markiert",
    dReports: "Zum Anpassen von Hand gemeldet",
    dCorrections: "Zähler-Korrekturen",
    dNotes: "Hinweise beim Rückgängigmachen",
    newIdMark: "neue ID",
    previously: "vorher",
    duringUndo: "beim Rückgängigmachen",
    status_pending: "ausstehend",
    status_applied: "angewandt",
    status_failed: "nicht möglich",
    undoneAt: "rückgängig gemacht",
    oldRemoved: "altes Gerät entfernt, nicht mehr rückgängig zu machen",
    nothingElse: "Es mussten keine Geräte-Verweise umgeschrieben werden.",
    undo: "Rückgängig",
    undoConfirm: "Diesen Tausch rückgängig machen?",
    undone: "Tausch rückgängig gemacht.",
    error: "Fehler",
    entities: "Entitäten",
    pending: "Zähler-Korrekturen in Arbeit",
    isNew: "neu",
    since: "seit",
    today: "heute",
    yesterday: "gestern",
    unavailable: "nicht erreichbar",
    swappedHint: "Das als alt gewählte Gerät wurde nach dem neuen hinzugefügt. Vertauscht?",
    swapSides: "Alt und neu tauschen",
    identify: "Identifizieren",
    identifyHint: "Lässt das Gerät blinken oder piepen, damit du es findest.",
    pendingHint: "wird nach dem nächsten 5-Minuten-Lauf der Statistik angewandt, gegen",
  },
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

class NineLivesPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = { step: "select", oldId: "", newId: "", filter: "" };
    this._backups = [];
    this._deviceList = [];
    this._open = new Set();
    this._pending = [];
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._loadBackups();
      this._loadDevices();
      this._render();
    }
  }

  set narrow(narrow) {
    const changed = this._narrow !== narrow;
    this._narrow = narrow;
    if (changed && this._hass) this._render();
  }

  get _t() {
    const lang = (this._hass?.language || "en").split("-")[0];
    return STRINGS[lang] || STRINGS.en;
  }

  _deviceName(id) {
    const own = this._device?.(id);
    if (own) return own.name;
    const d = this._hass.devices[id];
    if (!d) return id;
    return d.name_by_user || d.name || id;
  }

  _entityLabel(entityId) {
    const state = this._hass.states[entityId];
    const name = state?.attributes.friendly_name;
    return name ? `${name} (${entityId})` : entityId;
  }

  // Old device: alphabetical. New device: the most recently added first.
  _devices(newestFirst) {
    const filter = this._state.filter.toLowerCase();
    return this._deviceList
      .map((d) => ({ ...d, label: this._deviceLabel(d) }))
      .filter((d) => !filter || d.label.toLowerCase().includes(filter))
      .sort((a, b) =>
        newestFirst ? b.created_at.localeCompare(a.created_at) : a.label.localeCompare(b.label)
      );
  }

  async _call(message) {
    try {
      return await this._hass.callWS(message);
    } catch (err) {
      this._state.error = err.message || String(err);
      this._render();
      throw err;
    }
  }

  async _loadBackups() {
    [this._backups, this._pending] = await Promise.all([
      this._call({ type: "nine_lives/backups" }),
      this._call({ type: "nine_lives/pending" }),
    ]);
    this._render();
    // Corrections are applied a few minutes after a swap; check back until done.
    clearTimeout(this._refresh);
    if (this._pending.length) this._refresh = setTimeout(() => this._loadBackups(), 60000);
  }

  disconnectedCallback() {
    clearTimeout(this._refresh);
  }

  _ids() {
    return { old_device_id: this._state.oldId, new_device_id: this._state.newId };
  }

  _reason(code) {
    return this._t[`reason_${code}`] || code;
  }

  _chosenPairs() {
    return this._state.pairs
      .filter((p) => p.new)
      .map((p) => ({ old: p.old, new: p.new, new_entity_id: p.useTidy ? p.tidy : null }));
  }

  async _propose() {
    const result = await this._call({ type: "nine_lives/propose", ...this._ids() });
    const byOld = Object.fromEntries(result.pairs.map((p) => [p.old, p.new]));
    const olds = [...result.pairs.map((p) => p.old), ...result.unmatched_old];
    this._state.newEntities = [...result.pairs.map((p) => p.new), ...result.unmatched_new];
    const tidy = result.suggested_ids || {};
    this._state.pairs = olds.map((old) => ({
      old,
      new: byOld[old] || "",
      tidy: tidy[old] || null,
      useTidy: Boolean(tidy[old]),
    }));
    this._go("pairs");
  }

  async _preview() {
    this._state.plan = await this._call({
      type: "nine_lives/preview",
      ...this._ids(),
      pairs: this._chosenPairs(),
    });
    this._go("preview");
  }

  async _apply() {
    if (!confirm(this._t.confirm)) return;
    await this._call({ type: "nine_lives/apply", ...this._ids(), pairs: this._chosenPairs() });
    this._go("done");
    this._loadBackups();
  }

  async _undo(backupId) {
    if (!confirm(this._t.undoConfirm)) return;
    const result = await this._call({ type: "nine_lives/undo", backup_id: backupId });
    this._state.message = [this._t.undone, ...result.notes].join(" ");
    this._loadBackups();
  }

  _go(step) {
    this._state.step = step;
    this._state.error = null;
    this._render();
  }

  _reset() {
    this._state = { step: "select", oldId: "", newId: "", filter: "" };
    this._loadDevices();
    this._render();
  }

  async _loadDevices() {
    this._deviceList = await this._call({ type: "nine_lives/devices" });
    this._render();
  }

  _device(id) {
    return this._deviceList.find((d) => d.id === id);
  }

  _locale() {
    return this._hass.locale?.language || this._hass.language;
  }

  // "new, today 18:46" for devices added within a week, "since 03/05/2025" otherwise.
  _age(device) {
    const t = this._t;
    const created = new Date(device.created_at);
    const days = (Date.now() - created) / 86400000;
    const locale = this._locale();
    if (days > 7) return `${t.since} ${created.toLocaleDateString(locale)}`;
    const time = created.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86400000).toDateString();
    const day =
      created.toDateString() === today
        ? t.today
        : created.toDateString() === yesterday
          ? t.yesterday
          : created.toLocaleDateString(locale);
    return `${t.isNew}, ${day} ${time}`;
  }

  _deviceLabel(d) {
    const area = d.area_id && this._hass.areas[d.area_id]?.name;
    const parts = [
      [d.manufacturer, d.model].filter(Boolean).join(" "),
      area,
      d.integration,
      this._age(d),
      d.available ? null : this._t.unavailable,
    ].filter(Boolean);
    return `${d.name} · ${parts.join(" · ")}`;
  }

  _stateText(entityId) {
    const state = this._hass.states[entityId];
    if (!state) return "";
    if (this._hass.formatEntityState) return this._hass.formatEntityState(state);
    const unit = state.attributes.unit_of_measurement;
    return unit ? `${state.state} ${unit}` : state.state;
  }

  async _identify(entityId) {
    await this._hass.callService("button", "press", { entity_id: entityId });
  }

  _identifyButton(deviceId, role) {
    const d = deviceId && this._device(deviceId);
    if (!d?.identify) return "";
    const text = role ? `${this._t.identify}: ${role}` : this._t.identify;
    return `<button class="small" data-identify="${esc(d.identify)}" title="${esc(this._t.identifyHint)}">${esc(text)}</button>`;
  }

  _renderSelect() {
    const t = this._t;
    const options = (selected, exclude, newestFirst) =>
      `<option value="">${esc(t.choose)}</option>` +
      this._devices(newestFirst)
        .filter((d) => d.id !== exclude)
        .map(
          (d) =>
            `<option value="${esc(d.id)}" ${d.id === selected ? "selected" : ""}>${esc(d.label)}</option>`
        )
        .join("");
    const s = this._state;
    const oldDevice = this._device(s.oldId);
    const newDevice = this._device(s.newId);
    const mixedUp = oldDevice && newDevice && oldDevice.created_at > newDevice.created_at;
    return `
      <p class="muted">${esc(t.intro)}</p>
      <input id="filter" type="search" placeholder="${esc(t.search)}" value="${esc(s.filter)}">
      <label>${esc(t.oldDevice)}<select id="old">${options(s.oldId, s.newId, false)}</select></label>
      ${this._identifyButton(s.oldId)}
      <label>${esc(t.newDevice)}<select id="new">${options(s.newId, s.oldId, true)}</select></label>
      ${this._identifyButton(s.newId)}
      ${mixedUp ? `<p class="warn">${esc(t.swappedHint)} <button id="swap-sides" class="small">${esc(t.swapSides)}</button></p>` : ""}
      <div class="actions">
        <button id="next" class="primary" ${s.oldId && s.newId ? "" : "disabled"}>${esc(t.next)}</button>
      </div>`;
  }

  _renderPairs() {
    const t = this._t;
    const s = this._state;
    const used = new Set(s.pairs.map((p) => p.new).filter(Boolean));
    const rows = s.pairs
      .map((p, i) => {
        const options =
          `<option value="">${esc(t.skip)}</option>` +
          s.newEntities
            .filter((n) => n === p.new || !used.has(n))
            .filter((n) => n.split(".")[0] === p.old.split(".")[0])
            .map(
              (n) =>
                `<option value="${esc(n)}" ${n === p.new ? "selected" : ""}>${esc(this._entityLabel(n))}</option>`
            )
            .join("");
        const tidy =
          p.tidy && p.new
            ? `<tr class="tidy"><td colspan="3"><label><input type="checkbox" data-tidy="${i}" ${p.useTidy ? "checked" : ""}>
                ${esc(t.tidy)}: <code>${esc(p.tidy)}</code> <span class="muted">(${esc(t.tidyHint)})</span></label></td></tr>`
            : "";
        const value = (id) =>
          id && this._stateText(id) ? `<div class="value">${esc(this._stateText(id))}</div>` : "";
        return `<tr><td>${esc(this._entityLabel(p.old))}${value(p.old)}</td><td class="arrow">←</td>
          <td><select data-pair="${i}">${options}</select>${value(p.new)}</td></tr>${tidy}`;
      })
      .join("");
    const free = s.newEntities.filter((n) => !used.has(n));
    return `
      <h2>${esc(this._deviceName(s.oldId))} → ${esc(this._deviceName(s.newId))}</h2>
      <p>${this._identifyButton(s.oldId, t.oldDevice)} ${this._identifyButton(s.newId, t.newDevice)}</p>
      <p class="muted">${esc(t.pairsHint)}</p>
      <table><tr><th>${esc(t.oldDevice)}</th><th></th><th>${esc(t.newDevice)}</th></tr>${rows}</table>
      ${free.length ? `<p class="muted">${esc(t.unmatchedNew)}: ${free.map(esc).join(", ")}</p>` : ""}
      <div class="actions">
        <button id="back">${esc(t.back)}</button>
        <button id="preview" class="primary" ${this._chosenPairs().length ? "" : "disabled"}>${esc(t.preview)}</button>
      </div>`;
  }

  _renderPreview() {
    const t = this._t;
    const plan = this._state.plan;
    const renames = plan.pairs
      .map((p) => `<li><code>${esc(p.new)}</code> → <code>${esc(p.final)}</code></li>`)
      .join("");
    const changes = plan.files.flatMap((f) => f.changes);
    const reviews = plan.files.flatMap((f) => f.reviews);
    const blocked = plan.files.filter((f) => f.blocked);
    const reports = plan.reports || [];
    const list = (items, fn) => `<ul>${items.map(fn).join("")}</ul>`;
    return `
      <h2>${esc(t.previewTitle)}</h2>
      <h3>${esc(t.renames)}</h3><ul>${renames}</ul>
      <h3>${esc(t.deviceChanges)}</h3>
      <ul><li>${esc(t.deviceArea)}</li><li>${esc(t.deviceDisable)}</li></ul>
      <h3>${esc(t.refs)}</h3>
      ${changes.length ? list(changes, (c) => `<li>${esc(c.path)}</li>`) : `<p class="muted">${esc(t.noRefs)}</p>`}
      ${reviews.length ? `<h3 class="warn">${esc(t.reviews)}</h3>` + list(reviews, (r) => `<li>${esc(r.path)}: ${esc(r.reason)}</li>`) : ""}
      ${blocked.length ? `<h3 class="warn">${esc(t.blocked)}</h3>` + list(blocked, (f) => `<li>${esc(f.kind)}: ${esc(this._reason(f.blocked))}</li>`) : ""}
      ${reports.length ? `<h3 class="warn">${esc(t.manual)}</h3>` + list(reports, (r) => `<li>${esc(r.where)}: ${esc(this._reason(r.reason))}</li>`) : ""}
      <div class="actions">
        <button id="back">${esc(t.back)}</button>
        <button id="apply" class="primary">${esc(t.apply)}</button>
      </div>`;
  }

  _renderDone() {
    const t = this._t;
    return `
      <p class="ok">${esc(t.done)}</p>
      <p class="muted">${esc(t.removeHint)}</p>
      <div class="actions"><button id="again" class="primary">${esc(t.again)}</button></div>`;
  }

  _renderPending() {
    const t = this._t;
    if (!this._pending.length) return "";
    const locale = this._hass.locale?.language || this._hass.language;
    const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 3, signDisplay: "always" });
    const time = (iso) => new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
    return `<h3>${esc(t.pending)}</h3><ul>${this._pending
      .map(
        (p) => `<li><code>${esc(p.statistic_id)}</code>: ${esc(number.format(p.adjustment))} ${esc(p.unit)}
          <span class="muted">– ${esc(t.pendingHint)} ${esc(time(p.due))}</span></li>`
      )
      .join("")}</ul>`;
  }

  _renderSwapDetails(b) {
    const t = this._t;
    const locale = this._locale();
    const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 3, signDisplay: "always" });
    const section = (title, items) =>
      items.length ? `<h4>${esc(title)}</h4><ul>${items.join("")}</ul>` : "";
    const pairs = b.pairs.map(
      (p) => `<li><code>${esc(p.new)}</code> → <code>${esc(p.final)}</code>${
        p.final !== p.old ? ` <span class="muted">(${esc(t.newIdMark)}, ${esc(t.previously)} <code>${esc(p.old)}</code>)</span>` : ""
      }</li>`
    );
    const corrections = (b.corrections || []).map(
      (c) => `<li><code>${esc(c.statistic_id)}</code>: ${esc(number.format(c.adjustment))} ${esc(c.unit)}
        <span class="muted">– ${esc(t[`status_${c.status}`] || c.status)}${c.phase === "undo" ? `, ${esc(t.duringUndo)}` : ""}</span></li>`
    );
    return `<div class="details">
      ${section(t.dEntities, pairs)}
      ${b.changes.length ? section(t.dChanges, b.changes.map((c) => `<li>${esc(c)}</li>`)) : `<p class="muted">${esc(t.nothingElse)}</p>`}
      ${section(t.dReviews, b.reviews.map((r) => `<li>${esc(r.path)}: ${esc(r.reason)}</li>`))}
      ${section(t.dReports, b.reports.map((r) => `<li>${esc(r.where)}: ${esc(this._reason(r.reason))}</li>`))}
      ${section(t.dCorrections, corrections)}
      ${section(t.dNotes, (b.notes || []).map((n) => `<li>${esc(n)}</li>`))}
    </div>`;
  }

  _renderBackups() {
    const t = this._t;
    if (!this._backups.length) return this._renderPending() + `<p class="muted">${esc(t.noHistory)}</p>`;
    const locale = this._locale();
    const when = (iso) => new Date(iso).toLocaleString(locale);
    return this._renderPending() + `<ul class="backups">${this._backups
      .map(
        (b) => `<li><details data-swap="${esc(b.backup_id)}" ${this._open.has(b.backup_id) ? "open" : ""}>
          <summary><span><strong>${esc(b.old_device)} → ${esc(b.new_device)}</strong><br>
          <span class="muted">${esc(when(b.created))} · ${esc(t.entities)}: ${b.pairs.length}${
            b.undone ? ` · ${esc(t.undoneAt)} ${esc(when(b.undone))}` : ""
          }${b.old_device_removed && !b.undone ? ` · ${esc(t.oldRemoved)}` : ""}</span></span>
          ${b.can_undo ? `<button data-undo="${esc(b.backup_id)}">${esc(t.undo)}</button>` : ""}</summary>
          ${this._renderSwapDetails(b)}</details></li>`
      )
      .join("")}</ul>`;
  }

  _render() {
    if (!this._hass) return;
    const t = this._t;
    const s = this._state;
    const body = {
      select: () => this._renderSelect(),
      pairs: () => this._renderPairs(),
      preview: () => this._renderPreview(),
      done: () => this._renderDone(),
    }[s.step]();
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <header>
        ${this._narrow ? `<button id="menu" class="icon" title="Menu">☰</button>` : ""}
        <h1>Nine Lives</h1>
      </header>
      <main>
        ${s.error ? `<p class="error">${esc(t.error)}: ${esc(s.error)}</p>` : ""}
        ${s.message ? `<p class="ok">${esc(s.message)}</p>` : ""}
        <section class="card">${body}</section>
        <section class="card"><h2>${esc(t.history)}</h2>${this._renderBackups()}</section>
      </main>`;
    this._bind();
  }

  _bind() {
    const $ = (sel) => this.shadowRoot.querySelector(sel);
    const on = (sel, ev, fn) => $(sel)?.addEventListener(ev, fn);
    on("#menu", "click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    on("#filter", "input", (e) => {
      this._state.filter = e.target.value;
      const pos = e.target.selectionStart;
      this._render();
      const input = $("#filter");
      input.focus();
      input.setSelectionRange(pos, pos);
    });
    on("#old", "change", (e) => {
      this._state.oldId = e.target.value;
      this._render();
    });
    on("#new", "change", (e) => {
      this._state.newId = e.target.value;
      this._render();
    });
    on("#next", "click", () => this._propose());
    on("#swap-sides", "click", () => {
      [this._state.oldId, this._state.newId] = [this._state.newId, this._state.oldId];
      this._render();
    });
    this.shadowRoot.querySelectorAll("button[data-identify]").forEach((el) =>
      el.addEventListener("click", (e) => this._identify(e.target.dataset.identify))
    );
    on("#back", "click", () => this._go(this._state.step === "preview" ? "pairs" : "select"));
    on("#preview", "click", () => this._preview());
    on("#apply", "click", () => this._apply());
    on("#again", "click", () => this._reset());
    this.shadowRoot.querySelectorAll("select[data-pair]").forEach((el) =>
      el.addEventListener("change", (e) => {
        this._state.pairs[Number(e.target.dataset.pair)].new = e.target.value;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("input[data-tidy]").forEach((el) =>
      el.addEventListener("change", (e) => {
        this._state.pairs[Number(e.target.dataset.tidy)].useTidy = e.target.checked;
      })
    );
    this.shadowRoot.querySelectorAll("button[data-undo]").forEach((el) =>
      el.addEventListener("click", (e) => {
        // The button sits in the summary; keep it from opening the details.
        e.preventDefault();
        this._state.message = null;
        this._undo(e.target.dataset.undo);
      })
    );
    this.shadowRoot.querySelectorAll("details[data-swap]").forEach((el) =>
      el.addEventListener("toggle", () => {
        if (el.open) this._open.add(el.dataset.swap);
        else this._open.delete(el.dataset.swap);
      })
    );
  }
}

const STYLE = `
  :host { display: block; min-height: 100%; background: var(--primary-background-color);
    color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  header { display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff); }
  header h1 { font-size: 20px; font-weight: 400; margin: 0; }
  main { max-width: 860px; margin: 0 auto; padding: 16px; }
  .card { background: var(--card-background-color, #fff); border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--divider-color); padding: 16px; margin-bottom: 16px; }
  h2 { font-size: 18px; font-weight: 500; margin: 0 0 8px; }
  h3 { font-size: 15px; font-weight: 500; margin: 16px 0 4px; }
  label { display: block; margin: 12px 0; font-weight: 500; }
  select, input { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px;
    font: inherit; color: inherit; background: var(--secondary-background-color);
    border: 1px solid var(--divider-color); border-radius: 6px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: 500; padding: 4px; }
  td { padding: 4px; vertical-align: middle; word-break: break-word; }
  td select { margin: 0; }
  .value { font-size: 13px; color: var(--secondary-text-color); margin-top: 2px; }
  tr.tidy td { padding-top: 0; font-size: 13px; }
  tr.tidy label { margin: 0 0 8px; font-weight: 400; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  tr.tidy input { width: auto; display: inline; margin: 0; }
  .arrow { width: 24px; text-align: center; color: var(--secondary-text-color); }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  button { font: inherit; padding: 8px 16px; border-radius: 6px; cursor: pointer;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button:disabled { opacity: .5; cursor: default; }
  button.small { padding: 4px 10px; font-size: 13px; }
  button.icon { border: 0; color: inherit; font-size: 20px; padding: 4px 8px; }
  .muted { color: var(--secondary-text-color); }
  .warn { color: var(--warning-color, #ff9800); }
  .error { color: var(--error-color, #db4437); }
  .ok { color: var(--success-color, #43a047); font-weight: 500; }
  code { font-size: 13px; }
  ul { padding-left: 20px; margin: 4px 0; }
  ul.backups { list-style: none; padding: 0; }
  ul.backups > li { padding: 8px 0; border-top: 1px solid var(--divider-color); }
  ul.backups summary { display: flex; justify-content: space-between; align-items: center; gap: 8px;
    cursor: pointer; list-style: none; }
  ul.backups summary::-webkit-details-marker { display: none; }
  ul.backups summary > span::before { content: "▸ "; color: var(--secondary-text-color); }
  ul.backups details[open] summary > span::before { content: "▾ "; }
  .details { margin: 8px 0 4px 18px; font-size: 14px; }
  .details h4 { font-size: 14px; font-weight: 500; margin: 10px 0 2px; }
  @media (max-width: 600px) { main { padding: 8px; } }
`;

customElements.define("nine-lives-panel", NineLivesPanel);
