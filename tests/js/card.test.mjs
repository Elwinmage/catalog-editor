// The card is a renderer: these tests give it a fake backend and drive the DOM.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const CODE = readFileSync(
  new URL("../../custom_components/reeftech_catalog_editor/frontend/reeftech-catalog-editor-card.js", import.meta.url),
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
    "equipment/item": [{ id: "eheim-200", label: "Eheim 200", source: "pack", thumb: "/t.webp", image: "/i.png" }, { id: "mine", label: "Mine", source: "user" }],
    "equipment/task": [{ id: "clean", label: "Clean", source: "pack" }],
    "equipment/category": [{ id: "heater", label: "Heater", source: "pack" }],
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
            { section: "equipment", kinds: ["task", "category", "item"], provider: providers ? "maintenance_hub" : null, schemas: true, schema_error: null },
            { section: "supplements", kinds: ["supplement"], provider: null, schemas: false, schema_error: null },
          ];
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
  const card = window.document.createElement("reeftech-catalog-editor-card");
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
  assert.match(text(root), /Tasks.*Categories.*Items/);
  assert.equal(root.querySelectorAll(".entry").length, 0 + 1 && 1);
  button(root, "Items").click();
  await until(() => root.querySelectorAll(".entry").length === 2);
  assert.match(text(root), /Eheim 200.*catalog/);
  assert.match(text(root), /Mine.*yours/);
  const search = root.querySelector("input[type=search]");
  type(window, search, "mine");
  assert.equal(root.querySelectorAll(".entry").length, 1);
  type(window, search, "zzz");
  assert.match(text(root), /Nothing here yet/);
});

test("a catalog nobody reads says so", async () => {
  const { root } = setup({ providers: false });
  await until(() => text(root).includes("No integration reading"));
  const { root: other } = setup();
  await until(() => other.querySelector(".tabs"));
  button(other, "Supplements").click();
  await until(() => text(other).includes("No integration reading"));
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
  await until(() => root.querySelectorAll(".entry").length === 2);
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

test("own entries can be deleted", async () => {
  const { root, calls } = setup();
  await until(() => button(root, "Items"));
  button(root, "Items").click();
  await until(() => root.querySelectorAll(".entry").length === 2);
  root.querySelectorAll(".entry")[1].click();
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
  assert.match(text(root), /#3 Acme X1.*in the catalog.*merged/);
  assert.match(text(root), /#4 Other.*open/);

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
  assert.equal(window.customCards.at(-1).type, "reeftech-catalog-editor-card");
  assert.equal(window.document.createElement("reeftech-catalog-editor-card").getCardSize(), 8);
  assert.equal(JSON.stringify(window.ReeftechCatalogEditorCard.getStubConfig()), "{}");
});
