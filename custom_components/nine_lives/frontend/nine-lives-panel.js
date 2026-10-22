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
    noRefs: "No automation, script or scene refers to the old device.",
    reviews: "Please check afterwards",
    blocked: "Not changed",
    apply: "Swap devices",
    confirm: "Swap the devices now? A backup is kept and the swap can be undone.",
    done: "Done. The new device now uses the old entity IDs.",
    removeHint: "Once everything works, remove the old device from its integration.",
    again: "Swap another device",
    history: "Recent swaps",
    noHistory: "No swaps to undo.",
    undo: "Undo",
    undoConfirm: "Undo this swap?",
    undone: "Swap undone.",
    error: "Error",
    entities: "Entities",
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
    noRefs: "Keine Automation, kein Skript und keine Szene verweist auf das alte Gerät.",
    reviews: "Bitte danach prüfen",
    blocked: "Nicht geändert",
    apply: "Geräte tauschen",
    confirm: "Geräte jetzt tauschen? Es wird eine Sicherung angelegt, der Tausch lässt sich rückgängig machen.",
    done: "Fertig. Das neue Gerät nutzt jetzt die alten Entity-IDs.",
    removeHint: "Wenn alles läuft, entferne das alte Gerät aus seiner Integration.",
    again: "Weiteres Gerät tauschen",
    history: "Letzte Tausche",
    noHistory: "Nichts zum Rückgängigmachen.",
    undo: "Rückgängig",
    undoConfirm: "Diesen Tausch rückgängig machen?",
    undone: "Tausch rückgängig gemacht.",
    error: "Fehler",
    entities: "Entitäten",
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
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._loadBackups();
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
    const d = this._hass.devices[id];
    if (!d) return id;
    return d.name_by_user || d.name || id;
  }

  _entityLabel(entityId) {
    const state = this._hass.states[entityId];
    const name = state?.attributes.friendly_name;
    return name ? `${name} (${entityId})` : entityId;
  }

  _devices() {
    const counts = {};
    for (const e of Object.values(this._hass.entities)) {
      if (e.device_id) counts[e.device_id] = (counts[e.device_id] || 0) + 1;
    }
    const filter = this._state.filter.toLowerCase();
    return Object.values(this._hass.devices)
      .filter((d) => counts[d.id] && !d.disabled_by)
      .map((d) => {
        const area = d.area_id && this._hass.areas[d.area_id]?.name;
        const extra = [d.manufacturer, d.model, area].filter(Boolean).join(", ");
        return { id: d.id, label: this._deviceName(d.id) + (extra ? ` · ${extra}` : "") };
      })
      .filter((d) => !filter || d.label.toLowerCase().includes(filter))
      .sort((a, b) => a.label.localeCompare(b.label));
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
    this._backups = await this._call({ type: "nine_lives/backups" });
    this._render();
  }

  _ids() {
    return { old_device_id: this._state.oldId, new_device_id: this._state.newId };
  }

  _chosenPairs() {
    return this._state.pairs.filter((p) => p.new);
  }

  async _propose() {
    const result = await this._call({ type: "nine_lives/propose", ...this._ids() });
    const byOld = Object.fromEntries(result.pairs.map((p) => [p.old, p.new]));
    const olds = [...result.pairs.map((p) => p.old), ...result.unmatched_old];
    this._state.newEntities = [...result.pairs.map((p) => p.new), ...result.unmatched_new];
    this._state.pairs = olds.map((old) => ({ old, new: byOld[old] || "" }));
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
    this._render();
  }

  _renderSelect() {
    const t = this._t;
    const devices = this._devices();
    const options = (selected, exclude) =>
      `<option value="">${esc(t.choose)}</option>` +
      devices
        .filter((d) => d.id !== exclude)
        .map(
          (d) =>
            `<option value="${esc(d.id)}" ${d.id === selected ? "selected" : ""}>${esc(d.label)}</option>`
        )
        .join("");
    const s = this._state;
    return `
      <p class="muted">${esc(t.intro)}</p>
      <input id="filter" type="search" placeholder="${esc(t.search)}" value="${esc(s.filter)}">
      <label>${esc(t.oldDevice)}<select id="old">${options(s.oldId, s.newId)}</select></label>
      <label>${esc(t.newDevice)}<select id="new">${options(s.newId, s.oldId)}</select></label>
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
        return `<tr><td>${esc(this._entityLabel(p.old))}</td><td class="arrow">←</td>
          <td><select data-pair="${i}">${options}</select></td></tr>`;
      })
      .join("");
    const free = s.newEntities.filter((n) => !used.has(n));
    return `
      <h2>${esc(this._deviceName(s.oldId))} → ${esc(this._deviceName(s.newId))}</h2>
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
      .map((p) => `<li><code>${esc(p.new)}</code> → <code>${esc(p.old)}</code></li>`)
      .join("");
    const changes = plan.files.flatMap((f) => f.changes);
    const reviews = plan.files.flatMap((f) => f.reviews);
    const blocked = plan.files.filter((f) => f.blocked);
    const list = (items, fn) => `<ul>${items.map(fn).join("")}</ul>`;
    return `
      <h2>${esc(t.previewTitle)}</h2>
      <h3>${esc(t.renames)}</h3><ul>${renames}</ul>
      <h3>${esc(t.deviceChanges)}</h3>
      <ul><li>${esc(t.deviceArea)}</li><li>${esc(t.deviceDisable)}</li></ul>
      <h3>${esc(t.refs)}</h3>
      ${changes.length ? list(changes, (c) => `<li>${esc(c.path)}</li>`) : `<p class="muted">${esc(t.noRefs)}</p>`}
      ${reviews.length ? `<h3 class="warn">${esc(t.reviews)}</h3>` + list(reviews, (r) => `<li>${esc(r.path)}: ${esc(r.reason)}</li>`) : ""}
      ${blocked.length ? `<h3 class="warn">${esc(t.blocked)}</h3>` + list(blocked, (f) => `<li>${esc(f.kind)}: ${esc(f.blocked)}</li>`) : ""}
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

  _renderBackups() {
    const t = this._t;
    if (!this._backups.length) return `<p class="muted">${esc(t.noHistory)}</p>`;
    const locale = this._hass.locale?.language || this._hass.language;
    return `<ul class="backups">${this._backups
      .map(
        (b) => `<li><span><strong>${esc(b.old_device)} → ${esc(b.new_device)}</strong><br>
          <span class="muted">${esc(new Date(b.created).toLocaleString(locale))} · ${esc(t.entities)}: ${b.entities.length}</span></span>
          <button data-undo="${esc(b.backup_id)}">${esc(t.undo)}</button></li>`
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
    this.shadowRoot.querySelectorAll("button[data-undo]").forEach((el) =>
      el.addEventListener("click", (e) => {
        this._state.message = null;
        this._undo(e.target.dataset.undo);
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
  .arrow { width: 24px; text-align: center; color: var(--secondary-text-color); }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  button { font: inherit; padding: 8px 16px; border-radius: 6px; cursor: pointer;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button:disabled { opacity: .5; cursor: default; }
  button.icon { border: 0; color: inherit; font-size: 20px; padding: 4px 8px; }
  .muted { color: var(--secondary-text-color); }
  .warn { color: var(--warning-color, #ff9800); }
  .error { color: var(--error-color, #db4437); }
  .ok { color: var(--success-color, #43a047); font-weight: 500; }
  code { font-size: 13px; }
  ul { padding-left: 20px; margin: 4px 0; }
  ul.backups { list-style: none; padding: 0; }
  ul.backups li { display: flex; justify-content: space-between; align-items: center; gap: 8px;
    padding: 8px 0; border-top: 1px solid var(--divider-color); }
  @media (max-width: 600px) { main { padding: 8px; } }
`;

customElements.define("nine-lives-panel", NineLivesPanel);
