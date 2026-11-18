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
    { name: "brand", required: true, type: "string", maxLength: 64 },
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
  ],
};

function setup({ language = "en", providers = true } = {}) {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only", pretendToBeVisual: true });
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
          ];
        case "translate":
          if (state.translateError) throw { code: "translate_failed", message: "no translation service answered" };
          return { translations: { fr: "Chauffage", de: "Heizung" } };
        case "refresh":
          return { refreshed: true };
        case "entries":
          return entries[`${fields.section}/${fields.kind}`] || [];
        case "form":
          return FORM;
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
      calls.push({ command: "upload", url, file: options.body.get("file").name });
      return { ok: state.uploadOk !== false, json: async () => state.uploadReply || { token: "tok1", preview: "data:image/webp;base64,AAAA", has_alpha: true } };
    },
  };
  const card = window.document.createElement("catalog-editor-card");
  window.document.body.append(card);
  card.setConfig({});
  card.hass = hass;
  return { window, card, calls, state, root: card.shadowRoot, entries };
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
  await until(() => button(root, "Supplements"));
  button(root, "Supplements").click();
  await until(() => text(root).includes("Acme (2)"));
  const groups = [...root.querySelectorAll("details.group")];
  assert.deepEqual(groups.map((g) => g.querySelector("summary").textContent), ["Acme (2)", "No brand (1)"]);
  assert.equal(root.querySelectorAll("details details").length, 0);
});

test("water tests are grouped by brand", async () => {
  const { root } = setup();
  await until(() => button(root, "Water tests"));
  button(root, "Water tests").click();
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
  await until(() => other.querySelector(".tabs"));
  card._s.catalogs[1].installed = null;
  button(other, "Supplements").click();
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
