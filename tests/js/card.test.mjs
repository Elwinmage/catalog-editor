// The card is a renderer: these tests give it a fake backend and drive the DOM.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const CODE = readFileSync(
  new URL("../../custom_components/catalog_editor/frontend/catalog-editor-card.js", import.meta.url),
  "utf8",
);

const FORM = {
  kind: "item",
  section: "equipment",
  title: "Item",
  has_visual: true,
  id_from: ["brand", "model"],
  fields: [
    { name: "category", required: true, type: "ref", ref: "categories" },
    { name: "brand", required: true, type: "brand", maxLength: 64 },
    { name: "name", required: true, type: "i18n", languages: ["en", "fr", "de"], required_languages: ["en"] },
    { name: "power_w", required: false, type: "number", exclusiveMinimum: 0 },
    { name: "count", required: false, type: "integer", minimum: 1 },
    { name: "inherit", required: false, type: "boolean", default: true },
    { name: "kind", required: true, type: "enum", options: ["a", "b"] },
    { name: "opt", required: false, type: "enum", options: ["x", "y"] },
    { name: "scopes", required: false, type: "multi_enum", options: ["aquarium", "pool", "home"] },
    { name: "icon", required: false, type: "icon" },
    { name: "limits", required: false, type: "bounded_int" },
    {
      name: "maintenance",
      required: false,
      type: "list",
      item: {
        type: "object",
        fields: [
          { name: "task", required: true, type: "ref", ref: "tasks" },
          { name: "schedule", required: true, type: "schedule" },
          { name: "regulatory", required: false, type: "boolean" },
        ],
      },
    },
    { name: "sizes", required: false, type: "list", item: { type: "integer", minimum: 1 } },
    { name: "range", required: false, type: "object", fields: [{ name: "min", required: false, type: "number" }] },
    { name: "odd", required: false, type: "json" },
    { name: "paint", required: false, type: "color" },
    {
      name: "parts",
      required: false,
      type: "list",
      item: {
        type: "object",
        fields: [
          { name: "color", required: true, type: "color" },
          { name: "shade", required: false, type: "color" },
        ],
      },
    },
  ],
};

function setup({ language = "en", providers = true, house = false, reeftank = false, storage = false } = {}) {
  // an address gives the page a session storage (without one it throws, and the card copes)
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only", pretendToBeVisual: true, ...(storage ? { url: "http://localhost/" } : {}) });
  const { window } = dom;
  window.eval(CODE);
  window.confirm = () => true;
  const calls = [];
  const state = {
    github: { connected: false, login: null },
    contribs: [],
    interval: 1,
    polls: [{ status: "pending", interval: 1 }, { status: "ok", login: "elwin" }],
    saveResult: { saved: true },
    contributeResult: { submitted: true, number: 7, url: "https://github.com/x/pull/7", appended: false },
  };
  const entries = {
    "equipment/item": [
      { id: "eheim-200", label: "Eheim 200", source: "pack", thumb: "/t.webp", image: "/i.png", brand: "Eheim", category: "heater" },
      { id: "eheim-300", label: "Eheim 300", source: "pack", brand: "Eheim", category: "heater" },
      { id: "tunze-1", label: "Tunze 1", source: "pack", brand: "Tunze", category: "pump" },
      { id: "mine", label: "Mine", source: "user" },
    ],
    "equipment/task": [{ id: "clean", label: "Clean", source: "pack" }],
    "equipment/category": [{ id: "heater", label: "Heater", source: "pack" }, { id: "pump", label: "Pump", source: "pack" }],
    "supplements/supplement": [
      { id: "a-kh", label: "A KH", source: "pack", brand: "Acme" },
      { id: "a-ca", label: "A Ca", source: "pack", brand: "Acme" },
      { id: "z-mg", label: "Z Mg", source: "user" },
    ],
    "fish/fish": [
      { id: "clownfish", label: "Clownfish", source: "pack", water_types: ["marine"] },
      { id: "guppy", label: "Guppy", source: "pack", water_types: ["freshwater", "brackish"] },
      { id: "molly", label: "Molly", source: "pack", water_types: ["freshwater"] },
    ],
    "water_tests/water_test": [
      { id: "rs-kit", label: "Red Sea Kit", source: "pack", brand: "Red Sea" },
      { id: "rs-nitrate", label: "Red Sea Nitrate", source: "pack", brand: "Red Sea" },
    ],
  };
  const hass = {
    language,
    async callWS(msg) {
      const { type, ...fields } = msg;
      const command = type.split("/")[1];
      calls.push({ command, ...fields });
      switch (command) {
        case "catalogs":
          return [
            { section: "equipment", kinds: ["item", "category", "task"], installed: providers ? "1.0.0" : null, latest: "1.0.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null },
            { section: "supplements", kinds: ["supplement"], installed: providers ? "1.0.0" : null, latest: "1.0.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null },
            { section: "water_tests", kinds: ["water_test"], installed: providers ? "1.0.0" : null, latest: "1.0.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null },
            ...(house
              ? [
                  { section: "trees", kinds: ["tree"], installed: "1.0.0", latest: "1.0.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null },
                  { section: "objects", kinds: ["object"], installed: "1.0.0", latest: "1.0.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null },
                ]
              : []),
            ...(reeftank
              ? ["fish", "corals", "plants", "invertebrates"].map((section) => ({ section, kinds: [section.replace(/s$/, "")], installed: "2026.11.0", latest: "2026.11.0", update_available: false, in_progress: false, error: null, schemas: true, schema_error: null }))
              : []),
          ];
        case "image_status":
          return state.imageStatus || { configured: true, provider: "gemini", model: "gemini-x", providers: [], keys: ["magenta", "green"], licenses: ["CC BY 4.0", "CC0"] };
        case "image_prompt":
          return { prompt: `Realistic side view of ${fields.species}, on ${fields.key}` };
        case "image_generate":
          if (state.generateError) throw state.generateError;
          return state.photoReply || { token: "ph1", width: 640, height: 400, problems: [], key: "magenta", source: { type: "ai-generated", model: "gemini-x" }, preview: "data:image/webp;base64,BBBB" };
        case "atlas_view":
          calls.push({ command: "atlas_view_reply" });
          return state.atlasView || { frame: [208, 100], columns: 8, facing: "right", degraded: true, image: "data:image/webp;base64,SSSS", clips: { swim: { from: 0, to: 42, fps: 24, loop: true }, idle: { from: 43, to: 87, fps: 12, loop: true }, turn: { from: 88, to: 113, fps: 24, loop: false } } };
        case "image_build":
          if (state.buildError) throw state.buildError;
          return { token: "at1", preview: "data:image/webp;base64,CCCC", frame: [208, 120], source: { type: "ai-generated" } };
        case "translate":
          if (state.translateError) throw { code: "translate_failed", message: "no translation service answered" };
          return { translations: { fr: "Chauffage", de: "Heizung" } };
        case "refresh":
          return { refreshed: true };
        case "entries":
          return entries[`${fields.section}/${fields.kind}`] || [];
        case "brands":
          return [{ key: "redsea", name: "Red Sea", count: 3 }];
        case "form":
          return state.form || FORM;
        case "entry":
          return {
            data: { category: "heater", brand: "Eheim", name: { en: "Eheim 200" } },
            source: fields.entry_id === "mine" ? "user" : "pack",
            image: "/i.png",
            thumb: "/t.webp",
            user_copy: fields.entry_id === "mine",
          };
        case "validate":
          return state.validate ? state.validate(fields) : { errors: [], warnings: [] };
        case "suggest_id":
          return { id: "acme-x1" };
        case "save":
          return state.saveResult;
        case "delete":
          return { deleted: true };
        case "github_status":
          return { ...state.github, login_pending: false };
        case "github_login":
          return { user_code: "ABCD-1234", verification_uri: "https://github.com/login/device", expires_in: 900, interval: state.interval };
        case "github_login_poll": {
          const next = state.polls.shift();
          if (next.status === "ok") state.github = { connected: true, login: "elwin" };
          return next;
        }
        case "github_logout":
          state.github = { connected: false, login: null };
          return { connected: false };
        case "contributions":
          return state.contribs;
        case "pending":
          return [
            { section: "equipment", kind: "task", id: "rinse", label: "Rinse", open_pr: null },
            { section: "equipment", kind: "item", id: "mine", label: "Mine", open_pr: null },
            { section: "equipment", kind: "item", id: "sent", label: "Sent", open_pr: 4 },
          ];
        case "contribute_batch":
          if (state.expireOnce) {
            state.expireOnce = false;
            state.github = { connected: false, login: null };
            throw { code: "auth_required", message: "GitHub login expired or revoked" };
          }
          return state.batchResult || { submitted: true, number: 9, url: "https://github.com/x/pull/9", count: 2, skipped: [] };
        case "contribute":
          if (state.expireOnce) {
            state.expireOnce = false;
            state.github = { connected: false, login: null };
            throw { code: "auth_required", message: "GitHub login expired or revoked" };
          }
          return state.contributeResult;
        default:
          throw new Error(`unexpected ${command}`);
      }
    },
    async fetchWithAuth(url, options) {
      if (url.endsWith("/photo")) {
        calls.push({ command: "photo", url, key: options.body.get("key"), kind: options.body.get("kind") });
        return { ok: state.photoOk !== false, json: async () => state.photoUpload || { token: "ph2", width: 640, height: 400, problems: [], key: "magenta", source: { type: "photo" }, preview: "data:image/webp;base64,DDDD", message: "refused" } };
      }
      calls.push({ command: "upload", url, file: options.body.get("file").name });
      return { ok: state.uploadOk !== false, json: async () => state.uploadReply || { token: "tok1", preview: "data:image/webp;base64,AAAA", has_alpha: true } };
    },
  };
  const card = window.document.createElement("catalog-editor-card");
  window.document.body.append(card);
  card.setConfig({});
  card.hass = hass;
  return { window, card, calls, state, hass, root: card.shadowRoot, entries };
}

const until = async (check, ms = 3000) => {
  const end = Date.now() + ms;
  for (;;) {
    const value = check();
    if (value) return value;
    if (Date.now() > end) throw new Error("timeout");
    await new Promise((r) => setTimeout(r, 15));
  }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const text = (root) => root.textContent.replace(/\s+/g, " ");
// Catalogs are picked in a drop-down list: select the option whose text starts with the label
const pick = (root, label) => {
  const select = root.querySelector("select.catalog-select");
  const option = [...select.options].find((o) => o.textContent.startsWith(label));
  select.value = option.value;
  select.dispatchEvent(new select.ownerDocument.defaultView.Event("change"));
};
const catalogOption = (root, label) => {
  const select = root.querySelector("select.catalog-select");
  return select && [...select.options].some((o) => o.textContent.startsWith(label));
};
const button = (root, label) => [...root.querySelectorAll("button")].find((b) => b.textContent.includes(label));
const type = (window, input, value) => {
  input.value = value;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
};
const change = (window, input) => input.dispatchEvent(new window.Event("change", { bubbles: true }));
const field = (root, label) => [...root.querySelectorAll(".field")].find((f) => f.querySelector(":scope > label")?.textContent.trim().startsWith(label));
const last = (calls, command) => calls.filter((c) => c.command === command).at(-1);

test("lists the entries of a catalog and filters them", async () => {
  const { window, root } = setup();
  await until(() => root.querySelectorAll(".entry").length);
  assert.match(text(root), /Equipment.*Supplements/);
  assert.match(text(root), /Items.*Categories.*Tasks/);
  assert.equal(root.querySelectorAll(".entry").length, 4);
  assert.match(text(root), /Eheim 200.*catalog/);
  assert.match(text(root), /Mine.*yours/);
  const search = root.querySelector("input[type=search]");
  type(window, search, "mine");
  assert.equal(root.querySelectorAll(".entry").length, 1);
  type(window, search, "zzz");
  assert.match(text(root), /Nothing here yet/);
});

test("items are a tree: brand, then category, then equipment, with counts", async () => {
  const { window, root } = setup();
  await until(() => root.querySelectorAll("details.group").length);
  const brands = [...root.querySelectorAll(".list > details.group")];
  assert.deepEqual(
    brands.map((b) => b.querySelector(":scope > summary").textContent),
    ["Eheim (2)", "Tunze (1)", "No brand (1)"],
  );
  const eheim = brands[0];
  assert.deepEqual(
    [...eheim.querySelectorAll(":scope > details > summary")].map((x) => x.textContent),
    ["Heater (2)"],
  );
  assert.equal(eheim.querySelectorAll("details .entry").length, 2);
  assert.match(brands[2].textContent, /No category \(1\)/);
  assert.equal(brands[0].open, false);
  // A search opens the branches that match
  const search = root.querySelector("input[type=search]");
  type(window, search, "tunze");
  const found = root.querySelectorAll("details.group");
  assert.equal(found.length, 2);
  assert.equal([...found].every((d) => d.open), true);
});

test("supplements are grouped by brand only", async () => {
  const { root } = setup();
  await until(() => catalogOption(root, "Supplements"));
  pick(root, "Supplements");
  await until(() => text(root).includes("Acme (2)"));
  const groups = [...root.querySelectorAll("details.group")];
  assert.deepEqual(groups.map((g) => g.querySelector("summary").textContent), ["Acme (2)", "No brand (1)"]);
  assert.equal(root.querySelectorAll("details details").length, 0);
});

test("water tests are grouped by brand", async () => {
  const { root } = setup();
  await until(() => catalogOption(root, "Water tests"));
  pick(root, "Water tests");
  await until(() => text(root).includes("Red Sea (2)"));
  const groups = [...root.querySelectorAll("details.group")];
  assert.deepEqual(groups.map((g) => g.querySelector("summary").textContent), ["Red Sea (2)"]);
});

test("categories and tasks are flat lists", async () => {
  const { root } = setup();
  await until(() => button(root, "Categories"));
  button(root, "Categories").click();
  await until(() => root.querySelectorAll(".entry").length === 2);
  assert.equal(root.querySelectorAll("details.group").length, 0);
});

test("a catalog not downloaded offers to download it", async () => {
  const { root, calls, state } = setup({ providers: false });
  await until(() => text(root).includes("not downloaded yet"));
  state.downloaded = true;
  button(root, "Download").click();
  await until(() => calls.some((c) => c.command === "refresh" && c.section === "equipment"));
  const { root: other, card } = setup();
  await until(() => other.querySelector("select.catalog-select"));
  card._s.catalogs[1].installed = null;
  pick(other, "Supplements");
  await until(() => text(other).includes("not downloaded yet"));
});

test("an installed catalog shows its version and can be refreshed", async () => {
  const { root, calls, state } = setup();
  await until(() => text(root).includes("Catalog 1.0.0"));
  state.latest = "1.1.0";
  button(root, "Check for updates").click();
  await until(() => calls.some((c) => c.command === "refresh"));
});

test("is shown in French", async () => {
  const { root } = setup({ language: "fr" });
  await until(() => text(root).includes("Éditeur de catalogue"));
  assert.match(text(root), /Équipements/);
  assert.match(text(root), /Nouveau/);
});

test("builds the form of a new entry and sends what was typed", async () => {
  const { window, root, calls, state } = setup();
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => root.querySelector("fieldset") || field(root, "brand"));

  // Text, id suggestion and validation
  type(window, field(root, "brand").querySelector("input"), "Acme");
  const nameInput = field(root, "name").querySelector("input");
  type(window, nameInput, "Acme X1");
  await until(() => root.querySelector("input[disabled]") === null && last(calls, "suggest_id"));
  const idInput = root.querySelector(".field input");
  await until(() => idInput.value === "acme-x1");
  assert.equal(JSON.stringify(last(calls, "suggest_id").data.name), '{"en":"Acme X1"}');

  // Other languages sit in a collapsed block
  const more = field(root, "name").querySelector("details");
  type(window, more.querySelector("input"), "Acme français");
  assert.equal(field(root, "name").querySelectorAll("input").length >= 2, true);

  type(window, field(root, "power w").querySelector("input"), "12.5");
  type(window, field(root, "count").querySelector("input"), "3");
  const inherit = field(root, "inherit").querySelector("input");
  inherit.checked = false;
  change(window, inherit);
  const kind = field(root, "kind").querySelector("select");
  kind.value = "b";
  change(window, kind);
  const opt = field(root, "opt").querySelector("select");
  opt.value = "y";
  change(window, opt);
  const category = field(root, "category").querySelector("select");
  category.value = "heater";
  change(window, category);
  const scopes = field(root, "scopes").querySelectorAll("input");
  scopes[1].checked = true;
  change(window, scopes[1]);
  scopes[0].checked = true;
  change(window, scopes[0]);
  type(window, field(root, "icon").querySelector("input"), "mdi:heat");
  const limits = field(root, "limits").querySelectorAll("input");
  type(window, limits[0], "2");
  type(window, limits[1], "1");
  type(window, limits[2], "9");
  type(window, field(root, "range").querySelector("input"), "4");
  const odd = field(root, "odd").querySelector("textarea");
  type(window, odd, "{bad");
  assert.match(text(field(root, "odd")), /Not valid JSON/);
  type(window, odd, '{"a": 1}');
  assert.doesNotMatch(text(field(root, "odd")), /Not valid JSON/);

  // Lists: rows of integers and of objects with a schedule
  const sizes = field(root, "sizes");
  sizes.querySelector("button").click();
  type(window, sizes.querySelector("input"), "250");
  [...sizes.querySelectorAll("button")].at(-1).click();
  assert.equal(sizes.querySelectorAll(".item").length, 2);
  sizes.querySelectorAll(".item button")[1].click();
  assert.equal(sizes.querySelectorAll(".item").length, 1);

  const maintenance = field(root, "maintenance");
  maintenance.querySelector(":scope > div > button").click();
  const row = maintenance.querySelector(".item");
  const task = row.querySelector("select");
  task.value = "clean";
  change(window, task);
  const unit = [...row.querySelectorAll("select")].find((s) => [...s.options].some((o) => o.value === "weeks"));
  unit.value = "weeks";
  change(window, unit);
  const every = row.querySelectorAll("input[type=number]");
  type(window, every[0], "2");
  const schedule = [...row.querySelectorAll("select")].find((s) => [...s.options].some((o) => o.value === "seasonal"));
  schedule.value = "seasonal";
  change(window, schedule);
  const seasonal = row.querySelectorAll("input[type=number]");
  type(window, seasonal[0], "6");
  type(window, seasonal[1], "15");
  type(window, seasonal[2], "30");

  state.validate = ({ data }) => ({ errors: data.brand ? [] : ["brand: missing"], warnings: ["careful"] });
  await until(() => last(calls, "validate")?.data.maintenance);
  await sleep(600);
  const sent = last(calls, "validate");
  assert.equal(sent.entry_id, "acme-x1");
  assert.deepEqual(JSON.parse(JSON.stringify(sent.data)), {
    brand: "Acme",
    name: { en: "Acme X1", fr: "Acme français" },
    power_w: 12.5,
    count: 3,
    inherit: false,
    kind: "b",
    opt: "y",
    category: "heater",
    scopes: ["aquarium", "pool"],
    icon: "mdi:heat",
    limits: { default: 2, min: 1, max: 9 },
    range: { min: 4 },
    odd: { a: 1 },
    sizes: [250],
    maintenance: [{ task: "clean", schedule: { type: "seasonal", month: 6, day: 15, window_days: 30 } }],
  });
  assert.match(text(root), /careful/);

  // Saving a new entry
  const save = button(root, "Save");
  await until(() => !save.disabled);
  save.click();
  await until(() => last(calls, "save"));
  assert.equal(last(calls, "save").new, true);
  await until(() => text(root).includes("Saved"));
  assert.ok(root.querySelector(".list"));
});

test("editing an entry of the catalog, then a refused save", async () => {
  const { window, root, calls, state } = setup();
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => root.querySelectorAll(".entry").length === 4);
  root.querySelectorAll(".entry")[0].click();
  await until(() => text(root).includes("saving it creates your own version"));
  const idInput = root.querySelector(".field input");
  assert.equal(idInput.value, "eheim-200");
  assert.equal(idInput.disabled, true);
  assert.equal(field(root, "brand").querySelector("input").value, "Eheim");
  assert.equal(field(root, "category").querySelector("select").value, "heater");
  assert.equal(button(root, "Delete my copy"), undefined);

  state.saveResult = { saved: false, errors: ["category: unknown"], warnings: [] };
  state.validate = () => ({ errors: [], warnings: [] });
  const save = button(root, "Save");
  await until(() => !save.disabled);
  save.click();
  await until(() => text(root).includes("category: unknown"));
  assert.equal(last(calls, "save").new, false);
  assert.ok(root.querySelector("input[type=file]"));
});

test("an error from the backend is shown", async () => {
  const { window, root, card } = setup();
  await until(() => button(root, "Items"));
  card.hass = {
    ...card.hass,
    callWS: async () => {
      throw Object.assign(new Error("Schemas not downloaded yet"), { code: "schemas_unavailable" });
    },
  };
  button(root, "Items").click();
  await until(() => text(root).includes("Schemas not downloaded yet"));
});

test("errors and the GitHub code can be selected and copied", async () => {
  const { window, root, card } = setup();
  await until(() => button(root, "Items"));
  const copied = [];
  Object.defineProperty(window.navigator, "clipboard", { value: { writeText: async (t) => copied.push(t) }, configurable: true });
  card.hass = {
    ...card.hass,
    callWS: async (msg) => {
      if (msg.type.endsWith("github_login")) return { user_code: "ABCD-1234", verification_uri: "https://github.com/login/device", expires_in: 900, interval: 60 };
      throw new Error("Boom: not a fork");
    },
  };
  button(root, "Items").click();
  await until(() => text(root).includes("Boom: not a fork"));
  const error = root.querySelector(".msg.error");
  button(error, "Copy").click();
  await until(() => copied.length === 1);
  assert.equal(copied[0], "Boom: not a fork");
  await until(() => button(error, "Copied"));

  // The device code has its own button
  button(root, "Connect to GitHub").click();
  await until(() => root.querySelector(".code"));
  const row = root.querySelector(".code").parentElement;
  button(row, "Copy").click();
  await until(() => copied.length === 2);
  assert.equal(copied[1], "ABCD-1234");

  // Without a clipboard (not a secure context) the old way is used
  Object.defineProperty(window.navigator, "clipboard", { value: undefined, configurable: true });
  const commands = [];
  window.document.execCommand = (name) => commands.push(name);
  button(row, "Copy").click();
  await until(() => commands.length === 1);
  assert.deepEqual(commands, ["copy"]);

  // The styles do not forbid the selection
  const css = [...root.querySelectorAll("style")].map((n) => n.textContent).join("");
  assert.match(css, /\.msg, \.report, \.code[^}]*user-select: text/);
});

test("own entries can be deleted", async () => {
  const { root, calls } = setup();
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => root.querySelectorAll(".entry").length === 4);
  root.querySelectorAll(".entry")[3].click();
  await until(() => button(root, "Delete my copy"));
  button(root, "Delete my copy").click();
  await until(() => last(calls, "delete"));
  assert.equal(last(calls, "delete").entry_id, "mine");
  await until(() => text(root).includes("Deleted"));
});

test("uploads a picture and can drop it", async () => {
  const { window, root, calls, state } = setup();
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => root.querySelector("input[type=file]"));
  const input = root.querySelector("input[type=file]");
  Object.defineProperty(input, "files", { value: [new window.File(["x"], "pic.png", { type: "image/png" })] });
  change(window, input);
  await until(() => last(calls, "upload"));
  await until(() => root.querySelector(".picture img[src^='data:']"));
  await sleep(50);
  assert.equal((await until(() => last(calls, "validate"))).visual, "tok1");

  const remove = [...root.querySelectorAll(".picture input[type=checkbox]")][0];
  remove.checked = true;
  change(window, remove);
  await sleep(600);
  assert.equal(last(calls, "validate").remove_visual, true);
  assert.equal(last(calls, "validate").visual, undefined);

  // A picture without transparency, then a refused one
  state.uploadReply = { token: "tok2", preview: "data:image/webp;base64,BBBB", has_alpha: false };
  const again = root.querySelector("input[type=file]");
  Object.defineProperty(again, "files", { value: [new window.File(["x"], "b.jpg")] });
  change(window, again);
  await until(() => text(root).includes("No transparent background"));
  state.uploadOk = false;
  state.uploadReply = { message: "Picture refused: unreadable" };
  const third = root.querySelector("input[type=file]");
  Object.defineProperty(third, "files", { value: [new window.File(["x"], "c.jpg")] });
  change(window, third);
  await until(() => text(root).includes("Picture refused"));
  change(window, Object.assign(root.querySelector("input[type=file]"), {}));
});

test("signs in to GitHub with the device flow and proposes an entry", async () => {
  const { window, root, calls, state } = setup();
  await until(() => button(root, "Connect to GitHub"));
  button(root, "Connect to GitHub").click();
  await until(() => text(root).includes("ABCD-1234"));
  assert.match(text(root), /github.com\/login\/device/);
  await until(() => text(root).includes("Connected as elwin"), 5000);
  assert.equal(calls.filter((c) => c.command === "github_login_poll").length, 2);

  // A pull request is listed with its state
  state.contribs = [
    { number: 3, label: "Acme X1", url: "https://github.com/x/pull/3", kind: "item", id: "acme-x1", state: "merged", released: true },
    { number: 4, label: "Other", url: "https://github.com/x/pull/4", kind: "task", id: "o", state: "open", released: false },
    { number: 5, label: "Merged", url: "https://github.com/x/pull/5", kind: "task", id: "m", state: "merged", released: false },
    { number: 6, label: "Refused", url: "https://github.com/x/pull/6", kind: "task", id: "r", state: "closed", released: false },
  ];
  button(root, "Items").click();
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => field(root, "brand"));
  type(window, field(root, "brand").querySelector("input"), "Acme");
  const propose = button(root, "Save and propose");
  assert.equal(propose.disabled, true);
  const attest = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  attest.checked = true;
  change(window, attest);
  await until(() => !propose.disabled);
  propose.click();
  await until(() => last(calls, "contribute"));
  assert.equal(last(calls, "contribute").attest, true);
  await until(() => text(root).includes("Pull request opened: #7"));
  // Open pull requests by default; the other filters show the rest
  assert.match(text(root), /#4 Other.*open/);
  assert.doesNotMatch(text(root), /#3 Acme|#5 Merged|#6 Refused/);
  assert.match(text(root), /Open \(1\).*Merged \(1\).*In the catalog \(1\).*All \(4\)/);
  button(root, "Merged (").click();
  assert.match(text(root), /#5 Merged/);
  assert.doesNotMatch(text(root), /#4 Other|#3 Acme/);
  button(root, "In the catalog (").click();
  assert.match(text(root), /#3 Acme X1.*in the catalog.*merged/);
  button(root, "All (").click();
  assert.match(text(root), /#6 Refused.*closed/);
  button(root, "Open (").click();

  // A new commit into the same pull request
  state.contributeResult = { submitted: true, number: 7, appended: true };
  button(root, "Items").click();
  await until(() => button(root, "New"));
  root.querySelectorAll(".entry")[0].click();
  await until(() => button(root, "Save and propose"));
  const again = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  again.checked = true;
  change(window, again);
  await until(() => !button(root, "Save and propose").disabled);
  button(root, "Save and propose").click();
  await until(() => text(root).includes("Added to your open pull request"));

  // Refused by the checks
  state.contributeResult = { submitted: false, errors: ["category: unknown"], warnings: [] };
  button(root, "Items").click();
  await until(() => button(root, "New"));
  root.querySelectorAll(".entry")[0].click();
  await until(() => button(root, "Save and propose"));
  const third = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  third.checked = true;
  change(window, third);
  await until(() => !button(root, "Save and propose").disabled);
  button(root, "Save and propose").click();
  await until(() => text(root).includes("category: unknown"));

  // Disconnect, refresh
  button(root, "Disconnect").click();
  await until(() => button(root, "Connect to GitHub"));
  button(root, "Refresh").click();
});

test("the login can expire or be refused", async () => {
  const { root, state } = setup();
  await until(() => button(root, "Connect to GitHub"));
  state.polls = [{ status: "expired" }];
  button(root, "Connect to GitHub").click();
  await until(() => text(root).includes("The code expired"), 4000);
  state.polls = [{ status: "denied" }];
  button(root, "Connect to GitHub").click();
  await until(() => text(root).includes("GitHub login refused"), 4000);
});

test("registers itself as a custom card", () => {
  const { window } = setup();
  assert.equal(window.customCards.at(-1).type, "catalog-editor-card");
  assert.equal(window.document.createElement("catalog-editor-card").getCardSize(), 8);
  assert.equal(JSON.stringify(window.CatalogEditorCard.getStubConfig()), "{}");
});

async function openNewItem(window, root) {
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => field(root, "icon"));
}

test("the icon field warns about a wrong prefix", async () => {
  const { window, root } = setup();
  await openNewItem(window, root);
  type(window, field(root, "icon").querySelector("input"), "fa:heat");
  assert.match(text(field(root, "icon")), /must start with mdi:/);
  type(window, field(root, "icon").querySelector("input"), "mdi:heat");
  assert.doesNotMatch(text(field(root, "icon")), /must start with/);
});

test("the icon field uses Home Assistant's picker once it is defined", async () => {
  const { window, root, calls } = setup();
  class FakePicker extends window.HTMLElement {}
  window.customElements.define("ha-icon-picker", FakePicker);
  await openNewItem(window, root);
  await until(() => field(root, "icon").querySelector("ha-icon-picker"));
  const picker = field(root, "icon").querySelector("ha-icon-picker");
  assert.equal(field(root, "icon").querySelector("input"), null);
  picker.dispatchEvent(new window.CustomEvent("value-changed", { detail: { value: "mdi:fish" } }));
  await until(() => calls.some((c) => c.command === "validate" && c.data && c.data.icon === "mdi:fish"));
  picker.dispatchEvent(new window.CustomEvent("value-changed", { detail: { value: "fa:x" } }));
  assert.match(text(field(root, "icon")), /must start with mdi:/);
});

test("a proposal refused for an expired token is sent after signing in again", async () => {
  const { window, root, calls, state, card } = setup();
  state.github = { connected: true, login: "elwin" };
  state.expireOnce = true;
  state.interval = 1;
  state.polls = [{ status: "ok", login: "elwin" }];
  await openNewItem(window, root);
  await card._githubStatus(); // the card read the status before the test set it
  type(window, field(root, "brand").querySelector("input"), "Acme");
  const attest = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  attest.checked = true;
  change(window, attest);
  await until(() => !button(root, "Save and propose").disabled);
  button(root, "Save and propose").click();
  await until(() => text(root).includes("ABCD-1234"));
  assert.equal(calls.filter((c) => c.command === "contribute").length, 1);
  await until(() => text(root).includes("Pull request opened: #7"), 6000);
  assert.equal(calls.filter((c) => c.command === "contribute").length, 2);
});

test("Translate fills the empty languages and keeps what was typed", async () => {
  const { window, root, calls, state } = setup();
  await openNewItem(window, root);
  const note = () => text(field(root, "name"));
  button(field(root, "name"), "Translate").click();
  assert.match(note(), /Write a text first/);
  const inputs = () => field(root, "name").querySelectorAll("input");
  type(window, inputs()[0], "Heater");
  type(window, inputs()[1], "Réchauffeur");
  button(field(root, "name"), "Translate").click();
  await until(() => calls.some((c) => c.command === "translate"));
  const sent = calls.find((c) => c.command === "translate");
  assert.deepEqual([sent.text, sent.source, sent.targets], ["Heater", "en", ["de"]]);
  await until(() => inputs()[2].value === "Heizung");
  assert.equal(inputs()[1].value, "Réchauffeur");
  assert.ok(inputs()[2].classList.contains("auto"));
  assert.match(note(), /Machine translation/);
  button(field(root, "name"), "Translate").click();
  assert.match(note(), /already filled/);
});

test("a failed translation says so", async () => {
  const { window, root, state } = setup();
  await openNewItem(window, root);
  state.translateError = true;
  type(window, field(root, "name").querySelector("input"), "Heater");
  button(field(root, "name"), "Translate").click();
  await until(() => text(field(root, "name")).includes("no translation service"));
});

test("a brand spelled differently from a known one is corrected in one click", async () => {
  const { window, root } = setup();
  await openNewItem(window, root);
  const input = field(root, "brand").querySelector("input");
  assert.equal(field(root, "brand").querySelector("datalist option").value, "Red Sea");
  type(window, input, "red-sea");
  assert.match(text(field(root, "brand")), /Same brand as « Red Sea »/);
  button(field(root, "brand"), "Use this spelling").click();
  assert.equal(input.value, "Red Sea");
  assert.doesNotMatch(text(field(root, "brand")), /Same brand as/);
});

test("Propose all sends the selected entries in one request, after the certification", async () => {
  const { root, calls, window, state } = setup();
  state.github = { connected: true, login: "elwin" };
  await until(() => button(root, "Propose all my entries"));
  button(root, "Propose all my entries").click();
  await until(() => text(root).includes("Rinse"));
  // What is already in an open pull request is not selected (and cannot be)
  const boxes = [...root.querySelectorAll(".entry input[type=checkbox]")];
  assert.deepEqual(boxes.map((b) => [b.checked, b.disabled]), [[true, false], [true, false], [false, true]]);
  assert.match(text(root), /already in the open pull request #4/);
  const go = button(root, "Propose the selected entries");
  assert.equal(go.disabled, true);
  const attest = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  attest.checked = true;
  change(window, attest);
  assert.equal(go.disabled, false);
  go.click();
  await until(() => text(root).includes("Pull request opened, entries: 2 (#9)"));
  assert.equal(
    JSON.stringify(last(calls, "contribute_batch").entries),
    JSON.stringify([
      { section: "equipment", kind: "task", entry_id: "rinse" },
      { section: "equipment", kind: "item", entry_id: "mine" },
    ]),
  );
});

test("a batch refused for an expired token is sent after signing in again", async () => {
  const { root, calls, window, state, card } = setup();
  state.github = { connected: true, login: "elwin" };
  state.expireOnce = true;
  state.polls = [{ status: "ok", login: "elwin" }];
  await card._githubStatus();
  await until(() => button(root, "Propose all my entries"));
  button(root, "Propose all my entries").click();
  await until(() => text(root).includes("Rinse"));
  const attest = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  attest.checked = true;
  change(window, attest);
  button(root, "Propose the selected entries").click();
  await until(() => text(root).includes("ABCD-1234"));
  await until(() => text(root).includes("Pull request opened, entries: 2 (#9)"), 6000);
  assert.equal(calls.filter((c) => c.command === "contribute_batch").length, 2);
});

test("the redsea icon prefix is accepted only where its icon set is registered", async () => {
  const { window, root } = setup();
  window.customIcons = { redsea: { getIcon() {}, getIconList() {} } };
  await openNewItem(window, root);
  const input = () => field(root, "icon").querySelector("input");
  type(window, input(), "redsea:gyre-off");
  assert.doesNotMatch(text(field(root, "icon")), /must start with/);
  type(window, input(), "fa:x");
  assert.match(text(field(root, "icon")), /must start with mdi:, redsea:/);
});

test("a colour is picked or typed, each following the other", async () => {
  const { window, root, calls } = setup();
  await openNewItem(window, root);
  const [picker, hex] = field(root, "paint").querySelectorAll("input");
  assert.equal(picker.type, "color");
  assert.equal(hex.value, "");
  assert.equal(picker.value, "#808080");
  // Typed: upper case is accepted and written the way the catalog wants it
  type(window, hex, "#3F7F35");
  assert.equal(picker.value, "#3f7f35");
  // Half typed: kept as it is (the checks will say so), the picker does not move
  type(window, hex, "#3f7");
  assert.equal(picker.value, "#3f7f35");
  // Picked
  type(window, picker, "#c98a2e");
  assert.equal(hex.value, "#c98a2e");
  // A new row of a list starts with the colours its schema requires
  [...field(root, "parts").querySelectorAll("button")].find((b) => b.textContent.includes("+")).click();
  const row = [...field(root, "parts").querySelectorAll("input[type=color]")];
  assert.deepEqual(row.map((input) => input.value), ["#808080", "#808080"]);
  await until(() => last(calls, "validate")?.data.parts);
  const sent = last(calls, "validate").data;
  assert.equal(sent.paint, "#c98a2e");
  assert.deepEqual(JSON.parse(JSON.stringify(sent.parts)), [{ color: "#808080" }]);
});

test("the catalogs of the house view are listed with the others, in the language of the user", async () => {
  for (const [language, trees, objects] of [
    ["en", "Trees (house view)", "Objects (house view)"],
    ["fr", "Arbres (vue maison)", "Objets (vue maison)"],
  ]) {
    const { root } = setup({ language, house: true });
    await until(() => catalogOption(root, trees));
    assert.ok(catalogOption(root, objects));
    // The catalogs of reeftech say so too
    assert.ok(catalogOption(root, language === "fr" ? "Équipements (reeftech)" : "Equipment (reeftech)"));
    pick(root, trees);
    await until(() => root.querySelector("select.catalog-select").value === "trees");
  }
});

test("a batch over two catalogs shows every pull request", async () => {
  const { root, window, state } = setup();
  state.github = { connected: true, login: "elwin" };
  state.batchResult = {
    submitted: true,
    number: 3,
    url: "https://github.com/a/pull/3",
    pulls: [
      { repo: "Elwinmage/house-catalog", number: 3, url: "https://github.com/a/pull/3", count: 1 },
      { repo: "Elwinmage/reeftech-catalog", number: 5, url: "https://github.com/b/pull/5", count: 1 },
    ],
    count: 2,
    skipped: [],
  };
  await until(() => button(root, "Propose all my entries"));
  button(root, "Propose all my entries").click();
  await until(() => text(root).includes("Rinse"));
  const attest = [...root.querySelectorAll("input[type=checkbox]")].at(-1);
  attest.checked = true;
  change(window, attest);
  button(root, "Propose the selected entries").click();
  await until(() => text(root).includes("Pull request opened, entries: 2 (#3, #5)"));
});

test("the catalogs of reeftank are listed with their family, in the language of the user", async () => {
  for (const [language, labels] of [
    ["en", ["Fish (reeftank)", "Corals (reeftank)", "Plants (reeftank)", "Invertebrates (reeftank)"]],
    ["fr", ["Poissons (reeftank)", "Coraux (reeftank)", "Plantes (reeftank)", "Invertébrés (reeftank)"]],
  ]) {
    const { root } = setup({ language, reeftank: true });
    await until(() => catalogOption(root, labels[0]));
    for (const label of labels) assert.ok(catalogOption(root, label), label);
    // a catalog is picked from the list, whatever their number
    assert.equal(root.querySelectorAll(".tabs button").length > 0, true);
    pick(root, labels[1]);
    await until(() => root.querySelector("select.catalog-select").value === "corals");
  }
});

test("a pair of numbers is edited as a range and sent once both are filled", async () => {
  const { window, root, calls, state } = setup({ reeftank: true });
  state.form = {
    kind: "fish",
    section: "fish",
    title: "Fish",
    description: null,
    has_visual: false,
    id_from: ["scientific"],
    visual_limits: { image: 1, thumb: 1 },
    fields: [{ name: "size_cm", required: true, type: "range", bounds: { minimum: 0.1 }, description: "Adult size" }],
  };
  await until(() => catalogOption(root, "Fish"));
  pick(root, "Fish");
  await until(() => button(root, "New"));
  button(root, "New").click();
  const box = await until(() => field(root, "size cm"));
  const [low, high] = box.querySelectorAll("input[type=number]");
  assert.equal(low.min, "0.1");
  type(window, low, "6");
  await sleep(50);
  // one value is not a size yet
  assert.equal(calls.filter((c) => c.command === "validate").some((c) => c.data.size_cm !== undefined), false);
  type(window, high, "11");
  await until(() => last(calls, "validate")?.data.size_cm);
  assert.deepEqual(JSON.parse(JSON.stringify(last(calls, "validate").data.size_cm)), [6, 11]);
  // emptying one takes the value away again
  type(window, low, "");
  await until(() => last(calls, "validate").data.size_cm === undefined);
});

test("species are filtered by the water they live in", async () => {
  const { root } = setup({ reeftank: true });
  await until(() => catalogOption(root, "Fish"));
  pick(root, "Fish");
  await until(() => root.querySelectorAll(".entry").length === 3);
  const tab = (name) => [...root.querySelectorAll(".tabs button")].find((b) => b.textContent.startsWith(name));
  assert.match(text(root), /All waters \(3\).*Marine \(1\).*Freshwater \(2\).*Brackish \(1\)/);
  tab("Freshwater").click();
  assert.equal(root.querySelectorAll(".entry").length, 2);
  assert.match(text(root), /Guppy/);
  assert.doesNotMatch(text(root), /Clownfish/);
  tab("Marine").click();
  assert.equal(root.querySelectorAll(".entry").length, 1);
  tab("All waters").click();
  assert.equal(root.querySelectorAll(".entry").length, 3);
});

test("a catalog without water types has no such filter", async () => {
  const { root } = setup();
  await until(() => root.querySelectorAll(".entry").length);
  assert.doesNotMatch(text(root), /All waters/);
});

test("a card built again goes back to the entry being edited", async () => {
  const { window, hass, root } = setup({ storage: true });
  await until(() => root.querySelectorAll(".entry").length);
  root.querySelectorAll(".entry")[0].click();
  await until(() => root.querySelector("h3")?.textContent === FORM.title);
  const power = await until(() => field(root, "power w"));
  type(window, power.querySelector("input"), "12.5");
  await sleep(50);
  // Home Assistant builds the card again: same page, a new element
  window.document.body.replaceChildren();
  const again = window.document.createElement("catalog-editor-card");
  window.document.body.append(again);
  again.setConfig({});
  again.hass = hass;
  const view = again.shadowRoot;
  await until(() => view.querySelector("h3")?.textContent === FORM.title);
  const back = await until(() => field(view, "power w"));
  assert.equal(back.querySelector("input").value, "12.5");
}, 10000);

test("without a remembered view the first catalog is shown", async () => {
  const { root } = setup({ storage: true });
  await until(() => root.querySelectorAll(".entry").length);
  assert.equal(root.querySelector("select.catalog-select").value, "equipment");
  assert.equal(field(root, "power w"), undefined);
});

const FISH_FORM = {
  kind: "fish",
  section: "fish",
  title: "Fish",
  description: null,
  has_visual: false,
  has_atlas: true,
  id_from: ["scientific"],
  visual_limits: { image: 1, thumb: 1 },
  fields: [{ name: "scientific", required: true, type: "text" }],
};

async function openNewFish(opts = {}) {
  const ctx = setup({ reeftank: true });
  ctx.state.form = FISH_FORM;
  const { root, window } = ctx;
  await until(() => catalogOption(root, "Fish"));
  pick(root, "Fish");
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => root.querySelector(".atlas"));
  return { ...ctx, window, opts };
}

test("a photo is generated, checked and turned into an animation attached to the draft", async () => {
  const { root, calls, state } = await openNewFish();
  assert.ok(button(root, "Show the prompt"));
  await until(() => button(root, "Generate the photo (gemini-x)"));
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".photo-preview"));
  assert.deepEqual(JSON.parse(JSON.stringify(last(calls, "image_generate"))), { command: "image_generate", section: "fish", kind: "fish", species: last(calls, "image_generate").species, key: "magenta" });
  assert.ok(root.textContent.includes("Generated by gemini-x"));
  // an AI photo has its model as source: no author nor license to type
  assert.equal(root.querySelector(".photo-author"), null);
  assert.equal(root.querySelector(".photo-force"), null);
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  assert.equal(last(calls, "image_build").photo, "ph1");
  assert.equal(last(calls, "image_build").force, false);
  assert.ok(root.textContent.includes("Animation ready"));
  // the animation goes with the draft
  await until(() => last(calls, "validate")?.atlas === "at1");
  state.saveResult = { saved: true };
});

test("the animation opens beside the form, plays the clips in one loop and follows a new atlas", async () => {
  const { root, calls, window } = await openNewFish();
  window.HTMLCanvasElement.prototype.getContext = () => null; // jsdom draws nothing
  // nothing to play before there is an animation
  assert.equal(button(root, "Play the animation"), undefined);
  await until(() => button(root, "Generate the photo (gemini-x)"));
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".photo-preview"));
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  button(root, "Play the animation").click();
  await until(() => root.querySelectorAll(".preview canvas").length === 1);
  // asked for the atlas that was just built, and the form is still there
  assert.equal(last(calls, "atlas_view").atlas, "at1");
  assert.ok(root.querySelector(".split > .main .atlas"));
  assert.equal(root.querySelector(".preview canvas").width, 208);
  assert.match(text(root), /Degraded animation/);
  // the background is a choice that does not rebuild the panel
  const background = root.querySelector(".preview-bg");
  background.value = "dark";
  background.dispatchEvent(new window.Event("change"));
  assert.ok(root.querySelector(".preview.bg-dark"));
  // each background has a style rule that reaches the canvas (the rule once looked for a
  // descendant of the panel instead of the panel itself, so the choice changed nothing)
  const css = root.querySelector("style").textContent;
  for (const name of ["water", "dark", "light"]) {
    const rule = css.match(new RegExp(`(\\.preview[^{]*\\.bg-${name}[^{]*)\\{`));
    assert.ok(rule, `a rule for ${name}`);
    background.value = name;
    background.dispatchEvent(new window.Event("change"));
    assert.ok(root.querySelector(rule[1].trim()), `the rule of ${name} matches the canvas`);
  }
  // a new atlas is played at once
  const before = calls.filter((c) => c.command === "atlas_view").length;
  button(root, "Keep it (build the animation)").click();
  await until(() => calls.filter((c) => c.command === "atlas_view").length === before + 1);
  button(root, "Close").click();
  assert.equal(root.querySelector(".preview"), null);
});

test("the preview chains stay, swim, turn, turn mirrored, then starts again", async () => {
  const { window } = setup();
  const Card = window.customElements.get("catalog-editor-card");
  const clips = {
    idle: { from: 43, to: 87, fps: 12, loop: true },
    swim: { from: 0, to: 42, fps: 24, loop: true },
    turn: { from: 88, to: 113, fps: 24, loop: false },
  };
  const list = Card.playlist(clips);
  assert.deepEqual(JSON.parse(JSON.stringify(list.map((step) => [step.name, step.flip]))), [["idle", false], ["swim", false], ["turn", false], ["turn", true]]);
  // a missing clip is skipped
  assert.equal(Card.playlist({ swim: clips.swim }).map((step) => step.name).join(), "swim");
  const at = (ms) => JSON.parse(JSON.stringify(Card.sequenceFrame(list, ms))); // plain objects: the card lives in another realm
  assert.deepEqual(at(0), { name: "idle", flip: false, index: 43 });
  assert.equal(at(1000 / 12 * 2 + 1).index, 45);
  // idle lasts 45 / 12 s, then swim begins
  assert.deepEqual(at(3750 + 1), { name: "swim", flip: false, index: 0 });
  assert.equal(at(3750 + 1800 + 1).name, "turn"); // 43 / 24 s of swimming
  assert.equal(at(3750 + 1800 + 1).flip, false);
  const secondTurn = 3750 + 1800 + 26 / 24 * 1000 + 1;
  assert.deepEqual(at(secondTurn), { name: "turn", flip: true, index: 88 });
  // after the second turn the loop starts again with stay
  const round = 3750 + 1800 + 2 * 26 / 24 * 1000;
  assert.deepEqual(at(round + 1), { name: "idle", flip: false, index: 43 });
});

test("the prompt is shown to be used with any tool", async () => {
  const { root, window, calls } = await openNewFish();
  type(window, root.querySelector(".atlas input[type=text]"), "Amphiprion percula");
  root.querySelector(".photo-key").value = "green";
  root.querySelector(".photo-key").dispatchEvent(new window.Event("change"));
  button(root, "Show the prompt").click();
  const box = await until(() => root.querySelector("textarea.prompt"));
  assert.equal(box.value, "Realistic side view of Amphiprion percula, on green");
  assert.equal(last(calls, "image_prompt").key, "green");
});

test("without a key the generation is not offered, but a photo can be sent", async () => {
  const ctx = setup({ reeftank: true });
  ctx.state.form = FISH_FORM;
  ctx.state.imageStatus = { configured: false, provider: null, model: null, providers: [], keys: ["magenta", "green"], licenses: ["CC BY 4.0", "CC0"] };
  const { root, window, calls } = ctx;
  await until(() => catalogOption(root, "Fish"));
  pick(root, "Fish");
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => root.textContent.includes("enter your own API key"));
  assert.equal(button(root, "Generate the photo (gemini-x)"), undefined);
  const input = root.querySelector(".photo-file");
  Object.defineProperty(input, "files", { value: [new window.File(["x"], "fish.png")] });
  input.dispatchEvent(new window.Event("change"));
  await until(() => root.querySelector(".photo-author"));
  assert.equal(last(calls, "photo").key, "magenta");
  // a photo needs its author and license
  type(window, root.querySelector(".photo-author"), "Jane");
  root.querySelector(".photo-license").value = "CC0";
  root.querySelector(".photo-license").dispatchEvent(new window.Event("change"));
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  const build = last(calls, "image_build");
  assert.equal(build.author, "Jane");
  assert.equal(build.license, "CC0");
});

test("a photo that fails the checks is built only on demand", async () => {
  const { root, calls, state } = await openNewFish();
  state.photoReply = { token: "ph3", width: 300, height: 200, problems: ["photo too small: 300 px wide"], key: "magenta", source: { type: "ai-generated", model: "gemini-x" }, preview: "data:image/webp;base64,EEEE" };
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".photo-force"));
  assert.ok(root.textContent.includes("photo too small"));
  root.querySelector(".photo-force").click();
  button(root, "Keep it (build the animation)").click();
  await until(() => last(calls, "image_build"));
  assert.equal(last(calls, "image_build").force, true);
});

test("a species with a real animation asks before replacing it, an error is shown", async () => {
  const { root, calls, state } = await openNewFish();
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".photo-preview"));
  state.buildError = { code: "real_animation", message: "This species already has an animation made from videos" };
  button(root, "Keep it (build the animation)").click();
  await until(() => root.textContent.includes("already has an animation"));
  assert.equal(root.querySelector(".atlas-preview"), null);
  await until(() => root.querySelector(".photo-force"));
  state.buildError = null;
  root.querySelector(".photo-force").click();
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  assert.equal(last(calls, "image_build").force, true);
  state.generateError = { code: "provider_quota", message: "quota" };
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.textContent.includes("quota"));
});

test("an animation is forgotten when the identifier changes", async () => {
  const { root, window } = await openNewFish();
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".photo-preview"));
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  const id = root.querySelector("input[type=text]");
  type(window, id, "amphiprion_percula");
  await until(() => !root.querySelector(".atlas-preview"));
});

test("the current animation of a species is described", async () => {
  const { root } = await openNewFish();
  assert.ok(root.textContent.includes("no picture yet"));
});

test("a refused photo upload shows its error", async () => {
  const { root, window, state } = await openNewFish();
  state.photoOk = false;
  const input = root.querySelector(".photo-file");
  Object.defineProperty(input, "files", { value: [new window.File(["x"], "fish.png")] });
  input.dispatchEvent(new window.Event("change"));
  await until(() => root.textContent.includes("refused"));
  input.dispatchEvent(new window.Event("change"));
});

const PLANT_FORM = { ...FISH_FORM, kind: "plant", section: "plants", title: "Plant" };

function plantReply(token, key, extra = {}) {
  return { token, width: 600, height: 800, problems: [], key, default_key: "magenta", advice: null, source: { type: "ai-generated", model: "gemini-x" }, preview: `data:image/webp;base64,RAW${token}`, keyed: `data:image/webp;base64,KEY${token}`, ...extra };
}

async function openNewPlant() {
  const ctx = setup({ reeftank: true });
  ctx.state.form = PLANT_FORM;
  const { root } = ctx;
  await until(() => catalogOption(root, "Plant"));
  pick(root, "Plant");
  await until(() => button(root, "New"));
  button(root, "New").click();
  await until(() => root.querySelector(".atlas"));
  return ctx;
}

test("a plant is shown keyed out, and tried again on the same or another background", async () => {
  const { root, calls, state } = await openNewPlant();
  assert.ok(root.querySelector(".atlas .help").textContent.includes("one specimen"));
  state.photoReply = plantReply("ph1", "magenta");
  await until(() => button(root, "Generate the photo (gemini-x)"));
  button(root, "Generate the photo (gemini-x)").click();
  await until(() => root.querySelector(".keyed-preview"));
  // the server chooses the background of a plant nobody chose for
  const first = last(calls, "image_generate");
  assert.equal(first.kind, "plant");
  assert.equal("key" in first, false);
  assert.ok(root.querySelector(".photo-preview"));
  assert.equal(root.querySelector(".history"), null); // one attempt: nothing to compare
  // the same background: the key is the one of the photo, now explicit
  state.photoReply = plantReply("ph2", "magenta", { problems: ["the plant touches the edge of the picture"] });
  button(root, "Try again (same background)").click();
  await until(() => root.textContent.includes("touches the edge"));
  assert.equal(last(calls, "image_generate").key, "magenta");
  // another background, with the advice against green for a plant that is not listed
  state.photoReply = plantReply("ph3", "green", { advice: "green turns it grey" });
  button(root, "Try again on a green background").click();
  await until(() => root.querySelector(".advice"));
  assert.equal(last(calls, "image_generate").key, "green");
  assert.ok(root.querySelector(".advice").textContent.includes("green plant grey"));
  // the attempts stay, and one can be looked at again then kept
  await until(() => root.querySelectorAll(".history button").length === 3);
  root.querySelectorAll(".history button")[0].click();
  await until(() => root.querySelector(".history button.current") === root.querySelectorAll(".history button")[0]);
  button(root, "Keep it (build the animation)").click();
  await until(() => root.querySelector(".atlas-preview"));
  assert.equal(last(calls, "image_build").photo, "ph1");
});

test("a plant photo sent by hand says it is a plant's", async () => {
  const { root, window, calls } = await openNewPlant();
  const input = root.querySelector(".photo-file");
  Object.defineProperty(input, "files", { value: [new window.File(["x"], "plant.png")] });
  input.dispatchEvent(new window.Event("change"));
  await until(() => last(calls, "photo"));
  assert.equal(last(calls, "photo").kind, "plant");
});

test("a plant has a picture to look at, not a loop of clips", async () => {
  const { window } = await openNewPlant();
  const Card = window.customElements.get("catalog-editor-card");
  const still = { still: { from: 0, to: 0, fps: 1, loop: false } };
  assert.equal(Card.playlist(still).map((step) => step.name).join(), "still");
});
