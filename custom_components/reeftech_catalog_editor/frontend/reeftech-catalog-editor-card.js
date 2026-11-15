/*
 * ReefTech catalog editor card.
 *
 * A plain renderer: everything it shows (catalogs, entries, the fields of a
 * form, the verdict of the checks, the pull requests) comes from the websocket
 * commands of the reeftech_catalog_editor integration, which reads the JSON
 * Schemas of the catalog. No build step, no dependency.
 */
(() => {
  "use strict";

  const DOMAIN = "reeftech_catalog_editor";

  const TEXTS = {
    en: {
      title: "Catalog editor",
      catalog_equipment: "Equipment",
      catalog_supplements: "Supplements",
      catalog_parameters: "Parameters",
      kind_task: "Tasks",
      kind_category: "Categories",
      kind_item: "Items",
      kind_supplement: "Supplements",
      kind_parameter: "Parameters",
      new: "New",
      search: "Search…",
      back: "Back",
      empty: "Nothing here yet.",
      no_provider: "No integration reading this catalog is loaded (install maintenance_hub, reef_maintenance, redsea or reeftank).",
      no_schemas: "The schemas of this catalog are not available yet",
      source_pack: "catalog",
      source_builtin: "catalog",
      source_user: "yours",
      id: "Identifier",
      id_help: "Lower case letters, digits, - and _",
      overrides: "This entry comes from the catalog: saving it creates your own version.",
      picture: "Picture",
      picture_help: "Any picture: it is converted to a transparent WebP (512 px) and a thumbnail.",
      remove_picture: "Remove the picture",
      uploading: "Processing the picture…",
      no_alpha: "No transparent background",
      validate_ok: "Everything checks out.",
      errors: "To fix",
      warnings: "Warnings",
      save: "Save",
      saved: "Saved: usable at once by the integrations.",
      delete: "Delete my copy",
      deleted: "Deleted.",
      confirm_delete: "Delete your copy of this entry?",
      propose: "Save and propose to the catalog",
      attest: "I certify that any picture is my own work (or I hold the rights) and I agree to publish it under CC BY 4.0.",
      proposed: "Pull request opened",
      proposed_update: "Added to your open pull request",
      github: "GitHub",
      connected_as: "Connected as",
      connect: "Connect to GitHub",
      disconnect: "Disconnect",
      connect_help: "Open the page below and type this code:",
      waiting: "Waiting for your confirmation on GitHub…",
      login_expired: "The code expired, try again.",
      login_denied: "GitHub login refused.",
      needs_github: "Connect to GitHub to propose entries to the catalog.",
      contributions: "Your pull requests",
      refresh: "Refresh",
      state_open: "open",
      state_merged: "merged",
      state_closed: "closed",
      released: "in the catalog",
      add_item: "Add",
      remove: "Remove",
      other_languages: "Other languages",
      interval: "Every",
      seasonal: "Each year",
      unit: "Unit",
      default: "default",
      min: "min",
      max: "max",
      month: "Month",
      day: "Day",
      window_days: "Days before",
      invalid_json: "Not valid JSON",
      choose: "—",
      error: "Error",
    },
    fr: {
      title: "Éditeur de catalogue",
      catalog_equipment: "Équipements",
      catalog_supplements: "Suppléments",
      catalog_parameters: "Paramètres",
      kind_task: "Tâches",
      kind_category: "Catégories",
      kind_item: "Éléments",
      kind_supplement: "Suppléments",
      kind_parameter: "Paramètres",
      new: "Nouveau",
      search: "Rechercher…",
      back: "Retour",
      empty: "Rien pour l'instant.",
      no_provider: "Aucune intégration lisant ce catalogue n'est chargée (installez maintenance_hub, reef_maintenance, redsea ou reeftank).",
      no_schemas: "Les schémas de ce catalogue ne sont pas encore disponibles",
      source_pack: "catalogue",
      source_builtin: "catalogue",
      source_user: "à vous",
      id: "Identifiant",
      id_help: "Minuscules, chiffres, - et _",
      overrides: "Cet élément vient du catalogue : l'enregistrer crée votre propre version.",
      picture: "Image",
      picture_help: "Toute image : elle est convertie en WebP transparent (512 px) avec une miniature.",
      remove_picture: "Retirer l'image",
      uploading: "Traitement de l'image…",
      no_alpha: "Pas de fond transparent",
      validate_ok: "Tout est en règle.",
      errors: "À corriger",
      warnings: "Avertissements",
      save: "Enregistrer",
      saved: "Enregistré : utilisable tout de suite par les intégrations.",
      delete: "Supprimer ma copie",
      deleted: "Supprimé.",
      confirm_delete: "Supprimer votre copie de cet élément ?",
      propose: "Enregistrer et proposer au catalogue",
      attest: "Je certifie que toute image est mon œuvre (ou que j'en détiens les droits) et j'accepte de la publier sous CC BY 4.0.",
      proposed: "Pull request ouverte",
      proposed_update: "Ajouté à votre pull request ouverte",
      github: "GitHub",
      connected_as: "Connecté en tant que",
      connect: "Se connecter à GitHub",
      disconnect: "Se déconnecter",
      connect_help: "Ouvrez la page ci-dessous et saisissez ce code :",
      waiting: "En attente de votre confirmation sur GitHub…",
      login_expired: "Le code a expiré, recommencez.",
      login_denied: "Connexion à GitHub refusée.",
      needs_github: "Connectez-vous à GitHub pour proposer des éléments au catalogue.",
      contributions: "Vos pull requests",
      refresh: "Actualiser",
      state_open: "ouverte",
      state_merged: "fusionnée",
      state_closed: "fermée",
      released: "dans le catalogue",
      add_item: "Ajouter",
      remove: "Retirer",
      other_languages: "Autres langues",
      interval: "Tous les",
      seasonal: "Chaque année",
      unit: "Unité",
      default: "défaut",
      min: "min",
      max: "max",
      month: "Mois",
      day: "Jour",
      window_days: "Jours avant",
      invalid_json: "JSON invalide",
      choose: "—",
      error: "Erreur",
    },
  };

  const STYLE = `
    :host { display: block; }
    ha-card, .card { display: block; padding: 16px; box-sizing: border-box; }
    h2 { margin: 0 0 12px; font-size: 1.3em; font-weight: 500; }
    h3 { margin: 16px 0 8px; font-size: 1.05em; font-weight: 500; }
    .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .tabs button, button.btn {
      border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color);
      border-radius: 16px; padding: 6px 14px; cursor: pointer; font: inherit;
    }
    .tabs button.on, button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
    button:disabled { opacity: 0.5; cursor: default; }
    button.danger { color: var(--error-color); border-color: var(--error-color); }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .grow { flex: 1; min-width: 0; }
    input, select, textarea {
      font: inherit; color: var(--primary-text-color); background: var(--card-background-color);
      border: 1px solid var(--divider-color); border-radius: 6px; padding: 6px 8px; box-sizing: border-box; max-width: 100%;
    }
    input[type=text], input[type=search], input:not([type]), select, textarea { width: 100%; }
    input[type=number] { width: 7em; }
    input[type=checkbox] { width: auto; }
    textarea { min-height: 5em; font-family: monospace; }
    .list { display: flex; flex-direction: column; margin-top: 8px; }
    .entry {
      display: flex; gap: 10px; align-items: center; padding: 8px 4px; cursor: pointer;
      border-bottom: 1px solid var(--divider-color); background: none; border-left: 0; border-right: 0; border-top: 0;
      color: inherit; font: inherit; text-align: left; width: 100%;
    }
    .entry img, .thumb { width: 40px; height: 40px; object-fit: contain; border-radius: 6px; background: var(--secondary-background-color); }
    .thumb.empty { display: inline-block; }
    .sub { color: var(--secondary-text-color); font-size: 0.85em; }
    .badge { border-radius: 10px; padding: 1px 8px; font-size: 0.75em; border: 1px solid var(--divider-color); color: var(--secondary-text-color); }
    .badge.user, .badge.open { color: var(--primary-color); border-color: var(--primary-color); }
    .badge.merged { color: var(--success-color, #43a047); border-color: var(--success-color, #43a047); }
    .field { margin: 10px 0; }
    .field > label, .label { display: block; font-weight: 500; margin-bottom: 3px; }
    .req { color: var(--error-color); }
    .help { color: var(--secondary-text-color); font-size: 0.82em; margin-top: 2px; }
    fieldset { border: 1px solid var(--divider-color); border-radius: 8px; margin: 6px 0; padding: 4px 10px 8px; }
    legend { color: var(--secondary-text-color); font-size: 0.9em; }
    .item { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0; }
    .checks { display: flex; flex-wrap: wrap; gap: 4px 14px; }
    .checks label { font-weight: normal; display: flex; align-items: center; gap: 4px; }
    .msg { margin: 10px 0; padding: 8px 12px; border-radius: 8px; }
    .msg.error { background: var(--error-color); color: #fff; }
    .msg.info { background: var(--secondary-background-color); }
    .report ul { margin: 4px 0 8px 18px; padding: 0; }
    .report .bad { color: var(--error-color); }
    .report .warn { color: var(--warning-color, #ef6c00); }
    .report .good { color: var(--success-color, #43a047); }
    .code { font-size: 1.6em; letter-spacing: 0.15em; font-family: monospace; margin: 6px 0; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; align-items: center; }
    .picture { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .picture img { width: 96px; height: 96px; object-fit: contain; background: var(--secondary-background-color); border-radius: 8px; }
    a { color: var(--primary-color); }
  `;

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "style") node.setAttribute("style", value);
      else if (key in node && key !== "list" && key !== "type") node[key] = value;
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === undefined || child === null || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const isEmpty = (value) =>
    value === undefined ||
    value === null ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0);

  const humanize = (name) => String(name).replace(/_/g, " ");

  class ReeftechCatalogEditorCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._s = {
        catalogs: null,
        section: null,
        kind: null,
        entries: [],
        query: "",
        mode: "list",
        github: { connected: false, login: null },
        login: null,
        contribs: [],
        message: null,
        busy: false,
      };
      this._refs = {};
      this._started = false;
      this._timers = {};
    }

    // -- Home Assistant contract -------------------------------------------------

    setConfig(config) {
      this._config = config || {};
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._started) {
        this._started = true;
        this._start();
      }
    }

    get hass() {
      return this._hass;
    }

    getCardSize() {
      return 8;
    }

    static getStubConfig() {
      return {};
    }

    disconnectedCallback() {
      Object.values(this._timers).forEach(clearTimeout);
      this._timers = {};
      this._polling = false;
    }

    // -- helpers -----------------------------------------------------------------

    t(key) {
      const lang = ((this._hass && this._hass.language) || "en").slice(0, 2);
      return (TEXTS[lang] && TEXTS[lang][key]) || TEXTS.en[key] || key;
    }

    ws(command, fields) {
      return this._hass.callWS({ type: `${DOMAIN}/${command}`, ...(fields || {}) });
    }

    later(name, ms, fn) {
      clearTimeout(this._timers[name]);
      this._timers[name] = setTimeout(fn, ms);
    }

    fail(err) {
      this._s.message = { kind: "error", text: (err && err.message) || this.t("error") };
      if (err && err.code === "auth_required") this._githubStatus();
      this.render();
    }

    // -- start-up and navigation -------------------------------------------------

    async _start() {
      try {
        const [catalogs] = await Promise.all([this.ws("catalogs"), this._githubStatus(false)]);
        this._s.catalogs = catalogs;
        const first = catalogs.find((c) => c.provider) || catalogs[0];
        if (first) await this._openCatalog(first.section, first.kinds[0], false);
      } catch (err) {
        this.fail(err);
        return;
      }
      this.render();
    }

    async _githubStatus(redraw = true) {
      try {
        const status = await this.ws("github_status");
        this._s.github = { connected: status.connected, login: status.login };
        this._s.contribs = await this.ws("contributions");
      } catch (err) {
        this._s.message = { kind: "error", text: err.message };
      }
      if (redraw) this.render();
    }

    async _openCatalog(section, kind, redraw = true) {
      Object.assign(this._s, { section, kind, mode: "list", query: "", entries: [], message: null });
      this._refs = {};
      const info = (this._s.catalogs || []).find((c) => c.section === section);
      if (info && info.provider) {
        try {
          this._s.entries = await this.ws("entries", { section, kind });
        } catch (err) {
          this.fail(err);
          return;
        }
      }
      if (redraw) this.render();
    }

    // -- rendering: frame ----------------------------------------------------------

    render() {
      const s = this._s;
      const root = this.shadowRoot;
      root.replaceChildren(el("style", { text: STYLE }));
      const card = el("ha-card", { class: "card" }, el("h2", { text: this._config.title || this.t("title") }));
      if (s.catalogs) card.append(this._renderTabs());
      if (s.message) card.append(el("div", { class: `msg ${s.message.kind}`, text: s.message.text }));
      if (s.catalogs) card.append(s.mode === "form" ? this._renderForm() : this._renderList());
      if (s.catalogs) card.append(this._renderGithub());
      root.append(card);
    }

    _renderTabs() {
      const s = this._s;
      const wrap = el("div");
      const catalogs = el("div", { class: "tabs" });
      for (const catalog of s.catalogs) {
        catalogs.append(
          el("button", {
            class: catalog.section === s.section ? "on" : "",
            text: this.t(`catalog_${catalog.section}`),
            onclick: () => this._openCatalog(catalog.section, catalog.kinds[0]),
          }),
        );
      }
      wrap.append(catalogs);
      const info = s.catalogs.find((c) => c.section === s.section);
      if (info && info.kinds.length > 1) {
        const kinds = el("div", { class: "tabs" });
        for (const kind of info.kinds) {
          kinds.append(
            el("button", {
              class: kind === s.kind ? "on" : "",
              text: this.t(`kind_${kind}`),
              onclick: () => this._openCatalog(s.section, kind),
            }),
          );
        }
        wrap.append(kinds);
      }
      return wrap;
    }

    // -- rendering: list -----------------------------------------------------------

    _renderList() {
      const s = this._s;
      const info = s.catalogs.find((c) => c.section === s.section);
      const wrap = el("div");
      if (!info || !info.provider) {
        wrap.append(el("div", { class: "msg info", text: this.t("no_provider") }));
        return wrap;
      }
      if (!info.schemas) {
        wrap.append(el("div", { class: "msg info", text: `${this.t("no_schemas")}${info.schema_error ? `: ${info.schema_error}` : ""}` }));
      }
      const query = el("input", {
        type: "search",
        placeholder: this.t("search"),
        value: s.query,
        oninput: (event) => {
          s.query = event.target.value;
          this._fillList(list);
        },
      });
      wrap.append(
        el(
          "div",
          { class: "row" },
          el("div", { class: "grow" }, query),
          el("button", { class: "btn primary", text: `+ ${this.t("new")}`, disabled: !info.schemas, onclick: () => this._edit(null) }),
        ),
      );
      const list = el("div", { class: "list" });
      this._fillList(list);
      wrap.append(list);
      return wrap;
    }

    _fillList(list) {
      const s = this._s;
      const needle = s.query.trim().toLowerCase();
      const shown = s.entries.filter((e) => !needle || `${e.id} ${e.label}`.toLowerCase().includes(needle));
      list.replaceChildren();
      if (!shown.length) list.append(el("div", { class: "sub", text: this.t("empty") }));
      for (const entry of shown) {
        const source = entry.source === "user" ? "user" : "pack";
        list.append(
          el(
            "button",
            { class: "entry", onclick: () => this._edit(entry.id) },
            entry.thumb ? el("img", { src: entry.thumb, alt: "" }) : el("span", { class: "thumb empty" }),
            el("span", { class: "grow" }, el("div", { text: entry.label }), el("div", { class: "sub", text: entry.id })),
            el("span", { class: `badge ${source}`, text: this.t(`source_${source}`) }),
          ),
        );
      }
    }

    // -- the form ------------------------------------------------------------------

    async _edit(entryId) {
      const s = this._s;
      try {
        const form = await this.ws("form", { section: s.section, kind: s.kind });
        await this._preloadRefs(form.fields);
        let entry = { data: {}, source: null, image: null, thumb: null, user_copy: false };
        if (entryId !== null) {
          entry = await this.ws("entry", { section: s.section, kind: s.kind, entry_id: entryId });
        }
        Object.assign(s, {
          mode: "form",
          form,
          data: JSON.parse(JSON.stringify(entry.data)),
          entryId: entryId || "",
          isNew: entryId === null,
          idTouched: entryId !== null,
          origin: entry,
          upload: null,
          removeVisual: false,
          report: null,
          attest: false,
          message: null,
        });
        this.render();
        this._validateSoon(0);
      } catch (err) {
        this.fail(err);
      }
    }

    // Entries a `ref` field chooses from, by group of the merged catalog
    _refTarget(group) {
      const s = this._s;
      if (group === "tasks") return { section: "equipment", kind: "task" };
      if (group === "categories") return { section: "equipment", kind: "category" };
      return { section: s.section, kind: s.kind };
    }

    async _preloadRefs(fields) {
      const groups = new Set();
      const walk = (list) => {
        for (const field of list || []) {
          if (field.type === "ref") groups.add(field.ref);
          if (field.fields) walk(field.fields);
          if (field.item) walk([field.item]);
        }
      };
      walk(fields);
      for (const group of groups) {
        if (!this._refs[group]) this._refs[group] = await this.ws("entries", this._refTarget(group));
      }
    }

    _renderForm() {
      const s = this._s;
      const wrap = el("div");
      wrap.append(el("div", { class: "row" }, el("button", { class: "btn", text: `← ${this.t("back")}`, onclick: () => this._openCatalog(s.section, s.kind) }), el("h3", { class: "grow", text: s.form.title })));
      if (s.origin.source && s.origin.source !== "user") wrap.append(el("div", { class: "msg info", text: this.t("overrides") }));

      const idInput = el("input", {
        type: "text",
        value: s.entryId,
        disabled: !s.isNew,
        oninput: (event) => {
          s.entryId = event.target.value.trim();
          s.idTouched = true;
          this._validateSoon();
        },
      });
      this._idInput = idInput;
      wrap.append(el("div", { class: "field" }, el("label", { text: this.t("id") }, el("span", { class: "req", text: " *" })), idInput, el("div", { class: "help", text: this.t("id_help") })));

      for (const field of s.form.fields) wrap.append(this._field(field, () => s.data[field.name], (value) => this._setIn(s.data, field.name, value)));

      if (s.form.has_visual) wrap.append(this._renderPicture());
      this._reportBox = el("div", { class: "report" });
      wrap.append(this._reportBox);
      this._paintReport();
      wrap.append(this._renderActions());
      return wrap;
    }

    _setIn(object, key, value) {
      if (isEmpty(value) && value !== false && value !== 0) delete object[key];
      else object[key] = value;
      this._changed();
    }

    _changed() {
      this._validateSoon();
      this._suggestSoon();
    }

    // -- widgets -------------------------------------------------------------------

    _field(field, get, set) {
      const label = el("label", { text: humanize(field.name || "") }, field.required ? el("span", { class: "req", text: " *" }) : null);
      const box = el("div", { class: "field" });
      if (field.name) box.append(label);
      box.append(this._widget(field, get, set));
      if (field.description) box.append(el("div", { class: "help", text: field.description }));
      return box;
    }

    _widget(field, get, set) {
      switch (field.type) {
        case "string":
        case "id":
        case "icon":
          return this._text(field, get, set);
        case "number":
        case "integer":
          return this._number(field, get, set);
        case "boolean":
          return this._boolean(field, get, set);
        case "enum":
          return this._enum(field, get, set);
        case "multi_enum":
          return this._multi(field, get, set);
        case "i18n":
          return this._i18n(field, get, set);
        case "ref":
          return this._ref(field, get, set);
        case "bounded_int":
          return this._bounded(field, get, set);
        case "schedule":
          return this._schedule(field, get, set);
        case "object":
          return this._object(field, get, set);
        case "list":
          return this._list(field, get, set);
        default:
          return this._json(field, get, set);
      }
    }

    _text(field, get, set) {
      return el("input", {
        type: "text",
        value: get() ?? "",
        maxLength: field.maxLength,
        placeholder: field.type === "icon" ? "mdi:wrench" : undefined,
        oninput: (event) => set(event.target.value),
      });
    }

    _number(field, get, set) {
      const integer = field.type === "integer";
      const min = field.minimum ?? (field.exclusiveMinimum !== undefined ? field.exclusiveMinimum : undefined);
      return el("input", {
        type: "number",
        value: get() ?? "",
        min,
        max: field.maximum,
        step: integer ? "1" : "any",
        oninput: (event) => {
          const raw = event.target.value;
          set(raw === "" ? undefined : integer ? parseInt(raw, 10) : parseFloat(raw));
        },
      });
    }

    _boolean(field, get, set) {
      const current = get();
      return el("input", {
        type: "checkbox",
        checked: current === undefined ? field.default === true : current,
        onchange: (event) => set(event.target.checked),
      });
    }

    _enum(field, get, set) {
      const select = el("select", { onchange: (event) => set(event.target.value === "" ? undefined : event.target.value) });
      if (!field.required) select.append(el("option", { value: "", text: this.t("choose") }));
      for (const option of field.options) select.append(el("option", { value: option, text: String(option) }));
      select.value = get() ?? (field.required ? field.default ?? field.options[0] : "");
      if (field.required && get() === undefined) set(select.value);
      return select;
    }

    _multi(field, get, set) {
      const box = el("div", { class: "checks" });
      for (const option of field.options) {
        box.append(
          el(
            "label",
            {},
            el("input", {
              type: "checkbox",
              checked: (get() || []).includes(option),
              onchange: (event) => {
                const chosen = new Set(get() || []);
                if (event.target.checked) chosen.add(option);
                else chosen.delete(option);
                set(field.options.filter((o) => chosen.has(o)));
              },
            }),
            String(option),
          ),
        );
      }
      return box;
    }

    _i18n(field, get, set) {
      const languages = field.languages || ["en"];
      const required = new Set(field.required_languages || ["en"]);
      const row = (lang) =>
        el(
          "div",
          { class: "row" },
          el("span", { class: "sub", text: lang, style: "width:2em" }),
          el("div", { class: "grow" }, el("input", {
            type: "text",
            value: (get() || {})[lang] ?? "",
            oninput: (event) => {
              const next = { ...(get() || {}) };
              if (event.target.value === "") delete next[lang];
              else next[lang] = event.target.value;
              set(next);
            },
          })),
        );
      const main = languages.filter((l) => required.has(l) || (get() || {})[l]);
      const box = el("div", {}, main.map(row));
      const others = languages.filter((l) => !main.includes(l));
      if (others.length) box.append(el("details", {}, el("summary", { class: "sub", text: this.t("other_languages") }), others.map(row)));
      return box;
    }

    _ref(field, get, set) {
      const select = el("select", { onchange: (event) => set(event.target.value === "" ? undefined : event.target.value) });
      select.append(el("option", { value: "", text: this.t("choose") }));
      for (const entry of this._refs[field.ref] || []) select.append(el("option", { value: entry.id, text: `${entry.label} (${entry.id})` }));
      const current = get();
      if (current && !(this._refs[field.ref] || []).some((e) => e.id === current)) select.append(el("option", { value: current, text: current }));
      select.value = current ?? "";
      return select;
    }

    _bounded(field, get, set) {
      const part = (name) =>
        el(
          "label",
          { class: "sub" },
          `${this.t(name)} `,
          el("input", {
            type: "number",
            min: 1,
            step: 1,
            value: (get() || {})[name] ?? "",
            oninput: (event) => {
              const next = { ...(get() || {}) };
              if (event.target.value === "") delete next[name];
              else next[name] = parseInt(event.target.value, 10);
              set(Object.keys(next).length ? next : undefined);
            },
          }),
        );
      return el("div", { class: "row" }, part("default"), part("min"), part("max"));
    }

    _schedule(field, get, set) {
      const box = el("div");
      const draw = () => {
        box.replaceChildren();
        const value = get() || {};
        const type = value.type || "interval";
        box.append(
          el(
            "select",
            {
              onchange: (event) => {
                set(
                  event.target.value === "seasonal"
                    ? { type: "seasonal", month: 1, day: 1 }
                    : { type: "interval", unit: "months", every: { default: 1, min: 1, max: 12 } },
                );
                draw();
              },
            },
            ["interval", "seasonal"].map((name) => el("option", { value: name, text: this.t(name), selected: name === type })),
          ),
        );
        if (type === "seasonal") {
          const num = (name, min, max) =>
            el("label", { class: "sub" }, `${this.t(name)} `, el("input", {
              type: "number", min, max, step: 1, value: value[name] ?? "",
              oninput: (event) => {
                const next = { ...get() };
                if (event.target.value === "") delete next[name];
                else next[name] = parseInt(event.target.value, 10);
                set(next);
              },
            }));
          box.append(el("div", { class: "row" }, num("month", 1, 12), num("day", 1, 31), num("window_days", 0, 120)));
        } else {
          const unit = el("select", { onchange: (event) => set({ ...get(), unit: event.target.value }) }, ["days", "weeks", "months", "years"].map((u) => el("option", { value: u, text: u, selected: u === (value.unit || "months") })));
          box.append(el("div", { class: "row" }, unit, this._bounded({}, () => get()?.every, (every) => set({ ...get(), every }))));
        }
      };
      if (!get()) set({ type: "interval", unit: "months", every: { default: 1, min: 1, max: 12 } });
      draw();
      return box;
    }

    _object(field, get, set) {
      const box = el("fieldset");
      box.append(el("legend", { text: humanize(field.name || "") }));
      for (const sub of field.fields) {
        box.append(
          this._field(
            sub,
            () => (get() || {})[sub.name],
            (value) => {
              const next = { ...(get() || {}) };
              if (isEmpty(value) && value !== false && value !== 0) delete next[sub.name];
              else next[sub.name] = value;
              set(Object.keys(next).length ? next : undefined);
            },
          ),
        );
      }
      return box;
    }

    _list(field, get, set) {
      const box = el("div");
      const draw = () => {
        box.replaceChildren();
        const items = get() || [];
        items.forEach((_, index) => {
          const widget = this._widget(
            field.item,
            () => (get() || [])[index],
            (value) => {
              const next = [...(get() || [])];
              next[index] = value;
              set(next);
            },
          );
          box.append(
            el(
              "div",
              { class: "item" },
              el("div", { class: "grow" }, widget),
              el("button", {
                class: "btn danger",
                text: "×",
                title: this.t("remove"),
                onclick: () => {
                  const next = [...(get() || [])];
                  next.splice(index, 1);
                  set(next);
                  draw();
                },
              }),
            ),
          );
        });
        box.append(
          el("button", {
            class: "btn",
            text: `+ ${this.t("add_item")}`,
            onclick: () => {
              set([...(get() || []), this._blank(field.item)]);
              draw();
            },
          }),
        );
      };
      draw();
      return box;
    }

    // What a new row of a list starts with
    _blank(item) {
      switch (item.type) {
        case "object": {
          const row = {};
          for (const sub of item.fields) {
            if (sub.required && sub.type === "schedule") row[sub.name] = { type: "interval", unit: "months", every: { default: 1, min: 1, max: 12 } };
            else if (sub.default !== undefined) row[sub.name] = sub.default;
          }
          return row;
        }
        case "integer":
        case "number":
          return item.minimum ?? 1;
        case "enum":
          return item.options[0];
        default:
          return "";
      }
    }

    _json(field, get, set) {
      const area = el("textarea", { value: get() === undefined ? "" : JSON.stringify(get(), null, 2) });
      const note = el("div", { class: "help bad" });
      area.addEventListener("input", () => {
        try {
          set(area.value.trim() === "" ? undefined : JSON.parse(area.value));
          note.textContent = "";
        } catch {
          note.textContent = this.t("invalid_json");
        }
      });
      return el("div", {}, area, note);
    }

    // -- the picture ---------------------------------------------------------------

    _renderPicture() {
      const s = this._s;
      const box = el("div", { class: "field" }, el("div", { class: "label", text: this.t("picture") }));
      const preview = el("div", { class: "picture" });
      const draw = () => {
        preview.replaceChildren();
        const src = s.upload ? s.upload.preview : s.removeVisual ? null : s.origin.image || s.origin.thumb;
        if (src) preview.append(el("img", { src, alt: "" }));
        preview.append(
          el("input", {
            type: "file",
            accept: "image/png,image/jpeg,image/webp",
            onchange: (event) => this._upload(event.target.files[0]),
          }),
        );
        if (s.origin.image || s.upload) {
          preview.append(
            el("label", { class: "sub" }, el("input", {
              type: "checkbox",
              checked: s.removeVisual,
              onchange: (event) => {
                s.removeVisual = event.target.checked;
                if (s.removeVisual) s.upload = null;
                draw();
                this._validateSoon();
              },
            }), ` ${this.t("remove_picture")}`),
          );
        }
        if (s.upload && !s.upload.has_alpha) preview.append(el("div", { class: "sub bad", text: this.t("no_alpha") }));
      };
      draw();
      box.append(preview, el("div", { class: "help", text: this.t("picture_help") }));
      return box;
    }

    async _upload(file) {
      if (!file) return;
      const s = this._s;
      const body = new FormData();
      body.append("file", file);
      s.message = { kind: "info", text: this.t("uploading") };
      this.render();
      try {
        const reply = await this._hass.fetchWithAuth(`/api/${DOMAIN}/image`, { method: "POST", body });
        const payload = await reply.json();
        if (!reply.ok) throw new Error(payload.message || this.t("error"));
        s.upload = payload;
        s.removeVisual = false;
        s.message = null;
        this.render();
        this._validateSoon(0);
      } catch (err) {
        s.message = { kind: "error", text: err.message };
        this.render();
      }
    }

    // -- checks and actions --------------------------------------------------------

    _draft() {
      const s = this._s;
      return {
        section: s.section,
        kind: s.kind,
        entry_id: s.entryId,
        data: s.data,
        visual: s.upload ? s.upload.token : undefined,
        remove_visual: s.removeVisual,
      };
    }

    _validateSoon(delay = 500) {
      this.later("validate", delay, async () => {
        const s = this._s;
        if (s.mode !== "form") return;
        try {
          s.report = await this.ws("validate", this._draft());
        } catch (err) {
          s.report = { errors: [err.message], warnings: [] };
        }
        this._paintReport();
      });
    }

    _suggestSoon() {
      const s = this._s;
      if (!s.isNew || s.idTouched) return;
      this.later("suggest", 400, async () => {
        try {
          const { id } = await this.ws("suggest_id", { section: s.section, kind: s.kind, data: s.data });
          if (!s.idTouched && id) {
            s.entryId = id;
            if (this._idInput) this._idInput.value = id;
            this._validateSoon(0);
          }
        } catch {
          /* a suggestion is a convenience */
        }
      });
    }

    _paintReport() {
      const box = this._reportBox;
      const report = this._s.report;
      if (!box || !report) return;
      box.replaceChildren();
      if (report.errors.length) box.append(el("div", { class: "bad", text: this.t("errors") }), el("ul", { class: "bad" }, report.errors.map((e) => el("li", { text: e }))));
      if (report.warnings.length) box.append(el("div", { class: "warn", text: this.t("warnings") }), el("ul", { class: "warn" }, report.warnings.map((w) => el("li", { text: w }))));
      if (!report.errors.length && !report.warnings.length) box.append(el("div", { class: "good", text: this.t("validate_ok") }));
      if (this._saveButton) this._saveButton.disabled = report.errors.length > 0 || !this._s.entryId;
      if (this._proposeButton) this._proposeButton.disabled = report.errors.length > 0 || !this._s.entryId || !this._s.github.connected || !this._s.attest;
    }

    _renderActions() {
      const s = this._s;
      const bar = el("div", { class: "actions" });
      this._saveButton = el("button", { class: "btn primary", text: this.t("save"), disabled: true, onclick: () => this._save() });
      bar.append(this._saveButton);
      if (s.origin.user_copy) bar.append(el("button", { class: "btn danger", text: this.t("delete"), onclick: () => this._delete() }));
      const wrap = el("div", {}, bar);
      const propose = el("div", { class: "field" });
      if (!s.github.connected) propose.append(el("div", { class: "help", text: this.t("needs_github") }));
      propose.append(
        el("label", { class: "sub" }, el("input", {
          type: "checkbox",
          checked: s.attest,
          onchange: (event) => {
            s.attest = event.target.checked;
            this._paintReport();
          },
        }), ` ${this.t("attest")}`),
      );
      this._proposeButton = el("button", { class: "btn", text: this.t("propose"), disabled: true, onclick: () => this._propose() });
      propose.append(el("div", { class: "actions" }, this._proposeButton));
      wrap.append(propose);
      return wrap;
    }

    async _save() {
      const s = this._s;
      try {
        const result = await this.ws("save", { ...this._draft(), new: s.isNew });
        if (!result.saved) {
          s.report = result;
          this._paintReport();
          return false;
        }
        await this._openCatalog(s.section, s.kind, false);
        s.message = { kind: "info", text: this.t("saved") };
        this.render();
        return true;
      } catch (err) {
        this.fail(err);
        return false;
      }
    }

    async _propose() {
      const s = this._s;
      const entryId = s.entryId;
      const [section, kind] = [s.section, s.kind];
      if (!(await this._save())) return;
      try {
        const result = await this.ws("contribute", { section, kind, entry_id: entryId, attest: true });
        if (!result.submitted) {
          s.message = { kind: "error", text: result.errors.join(" ") };
        } else {
          s.message = { kind: "info", text: `${this.t(result.appended ? "proposed_update" : "proposed")}: #${result.number}` };
        }
        s.contribs = await this.ws("contributions");
        this.render();
      } catch (err) {
        this.fail(err);
      }
    }

    async _delete() {
      const s = this._s;
      if (!window.confirm(this.t("confirm_delete"))) return;
      try {
        await this.ws("delete", { section: s.section, kind: s.kind, entry_id: s.entryId });
        await this._openCatalog(s.section, s.kind, false);
        s.message = { kind: "info", text: this.t("deleted") };
        this.render();
      } catch (err) {
        this.fail(err);
      }
    }

    // -- GitHub --------------------------------------------------------------------

    _renderGithub() {
      const s = this._s;
      const box = el("div", {}, el("h3", { text: this.t("github") }));
      if (s.github.connected) {
        box.append(
          el(
            "div",
            { class: "row" },
            el("span", { class: "grow", text: `${this.t("connected_as")} ${s.github.login}` }),
            el("button", { class: "btn", text: this.t("disconnect"), onclick: () => this._logout() }),
          ),
        );
      } else if (s.login) {
        box.append(
          el("div", { class: "sub", text: this.t("connect_help") }),
          el("div", { class: "code", text: s.login.user_code }),
          el("a", { href: s.login.verification_uri, target: "_blank", rel: "noopener", text: s.login.verification_uri }),
          el("div", { class: "sub", text: this.t("waiting") }),
        );
      } else {
        box.append(el("button", { class: "btn", text: this.t("connect"), onclick: () => this._login() }));
      }
      if (s.contribs.length) {
        box.append(
          el("div", { class: "row" }, el("h3", { class: "grow", text: this.t("contributions") }), el("button", { class: "btn", text: this.t("refresh"), onclick: () => this._githubStatus() })),
          el(
            "div",
            { class: "list" },
            s.contribs.map((item) =>
              el(
                "div",
                { class: "entry" },
                el("span", { class: "grow" }, el("a", { href: item.url, target: "_blank", rel: "noopener", text: `#${item.number} ${item.label}` }), el("div", { class: "sub", text: `${item.kind} · ${item.id}` })),
                item.released ? el("span", { class: "badge merged", text: this.t("released") }) : null,
                el("span", { class: `badge ${item.state}`, text: this.t(`state_${item.state}`) }),
              ),
            ),
          ),
        );
      }
      return box;
    }

    async _login() {
      const s = this._s;
      try {
        s.login = await this.ws("github_login");
        s.message = null;
        this.render();
        this._polling = true;
        this._poll(s.login.interval);
      } catch (err) {
        this.fail(err);
      }
    }

    _poll(seconds) {
      this.later("poll", Math.max(seconds, 1) * 1000, async () => {
        if (!this._polling) return;
        const s = this._s;
        try {
          const result = await this.ws("github_login_poll");
          if (result.status === "pending") {
            this._poll(result.interval);
            return;
          }
          this._polling = false;
          s.login = null;
          if (result.status === "ok") await this._githubStatus(false);
          else s.message = { kind: "error", text: this.t(result.status === "expired" ? "login_expired" : "login_denied") };
          this.render();
          this._paintReport();
        } catch (err) {
          this._polling = false;
          s.login = null;
          this.fail(err);
        }
      });
    }

    async _logout() {
      try {
        await this.ws("github_logout");
        await this._githubStatus();
        this._paintReport();
      } catch (err) {
        this.fail(err);
      }
    }
  }

  if (!customElements.get("reeftech-catalog-editor-card")) {
    customElements.define("reeftech-catalog-editor-card", ReeftechCatalogEditorCard);
  }
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "reeftech-catalog-editor-card",
    name: "ReefTech catalog editor",
    description: "Add and edit entries of the ReefTech catalogs and propose them as pull requests.",
  });
  window.ReeftechCatalogEditorCard = ReeftechCatalogEditorCard;
})();
