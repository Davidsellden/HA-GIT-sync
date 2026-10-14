const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const staticDir = path.join(__dirname, "../app/static");

function panel({ha = "en", stored = null, inaccessible = false} = {}) {
  const elements = new Map(), calls = [], prompts = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value:"", checked:false, hidden:false, disabled:false, dataset:{}, options:[], children:[],
      textContent:"", listeners:{},
      addEventListener(type, handler) { this.listeners[type] = handler; },
      replaceChildren(...nodes) { this.children = nodes; },
      append(...nodes) { this.children.push(...nodes); },
      scrollIntoView() {},
    });
    return elements.get(id);
  }
  const parent = {document:{querySelector:() => ({hass:{language:ha}})}};
  parent.parent = parent;
  const window = {parent};
  if (inaccessible) Object.defineProperty(parent, "document", {get() { throw new Error("Cross origin"); }});
  const context = vm.createContext({
    window, localStorage:{getItem:() => stored}, setInterval() {},
    document:{getElementById:element, querySelectorAll:() => [], createElement:() => element(Symbol())},
    confirm(message) { prompts.push(message); return context.accept; },
    calls, accept:true, fetch() { throw new Error("Unexpected network request"); },
  });
  vm.runInContext(fs.readFileSync(path.join(staticDir,"i18n.js"),"utf8"), context);
  const source = fs.readFileSync(path.join(staticDir,"app.js"),"utf8").replace(/\r\n/g, "\n");
  vm.runInContext(source.slice(0, source.indexOf("initializeLanguage();\n")), context);
  vm.runInContext(`
    status = async () => ({});
    job = async (action, fields={}) => {
      calls.push({action, fields});
      if (action === "configure_scope") {
        if (failSave) throw new Error("Save failed");
        return fields;
      }
      return {branch:"main", commit:"1234567890", changes:[], new_branch:false};
    };
    selectedPaths = new Set(["configuration.yaml"]);
    savedScope = normalizedScope({includes:["configuration.yaml"], excludes:[]});
    language = resolveLanguage();
  `, context);
  context.failSave = false;
  element("push-branch").value = element("pull-branch").value = "main";
  return {context, element, calls, prompts, run: code => vm.runInContext(code, context)};
}

test("dirty checkboxes save before push preview", async () => {
  const p = panel(); p.run('selectedPaths.add("custom.yaml")');
  await p.run('preview("push")');
  assert.deepEqual(p.calls.map(c => c.action), ["configure_scope", "preview_push"]);
  assert.ok(p.calls[0].fields.includes.includes("custom.yaml"));
  assert.equal(p.run("scopeDirty()"), false);
  assert.match(p.prompts[0], /unsaved/);
});
test("cancel preserves draft and performs no sync", async () => {
  const p = panel(); p.context.accept = false;
  p.run('selectedPaths.add("custom.yaml")');
  await p.run('preview("push")');
  assert.equal(p.calls.length, 0);
  assert.equal(p.run("scopeDirty()"), true);
});
test("save failure prevents preview and preserves draft", async () => {
  const p = panel(); p.context.failSave = true;
  p.run('selectedPaths.add("custom.yaml")');
  await assert.rejects(p.run('preview("push")'), /Save failed/);
  assert.deepEqual(p.calls.map(c => c.action), ["configure_scope"]);
  assert.equal(p.run("scopeDirty()"), true);
});
test("extra paths and exclusions are saved before import", async () => {
  const p = panel(); p.element("extra-paths").value = "remote.yaml";
  p.element("exclude-paths").value = "packages/test.yaml";
  await p.run('preview("pull")');
  assert.deepEqual(p.calls.map(c => c.action), ["configure_scope", "preview_pull"]);
  assert.ok(p.calls[0].fields.includes.includes("remote.yaml"));
  assert.equal(p.calls[0].fields.excludes[0], "packages/test.yaml");
});
test("unchanged selection and reverted changes do not prompt", async () => {
  const p = panel(); p.run('selectedPaths.add("custom.yaml"); selectedPaths.delete("custom.yaml")');
  await p.run('preview("push")');
  assert.equal(p.prompts.length, 0);
  assert.deepEqual(p.calls.map(c => c.action), ["preview_push"]);
});
test("scope comparison ignores duplicate extra paths and ordering", () => {
  const p = panel(); p.element("extra-paths").value = "configuration.yaml\nconfiguration.yaml";
  assert.equal(p.run("scopeDirty()"), false);
});
test("HA Swedish is automatic, other languages and inaccessible HA use English", () => {
  for (const [ha, expected] of [["sv","sv"],["sv-SE","sv"],["de","en"],["en","en"]]) {
    assert.equal(panel({ha}).run("language"), expected);
  }
  assert.equal(panel({ha:"sv", inaccessible:true}).run("language"), "en");
});
test("manual language overrides HA; automatic follows changes", () => {
  assert.equal(panel({ha:"sv",stored:"en"}).run("language"), "en");
  assert.equal(panel({ha:"en",stored:"sv"}).run("language"), "sv");
  const p = panel({ha:"sv"});
  p.run('window.parent.document.querySelector = () => ({hass:{language:"fr"}})');
  assert.equal(p.run("resolveLanguage()"), "en");
});
test("status/errors/actions translate while filenames are preserved", () => {
  const p = panel();
  assert.equal(p.run('translateBackend("Granskning klar")'), "Preview ready");
  assert.equal(p.run('translateBackend("tas bort")'), "deleted");
  assert.equal(p.run('translateBackend("Branchen saknar dashboards/kök.yaml.")'), "The branch is missing dashboards/kök.yaml.");
  p.run('language = "sv"');
  assert.equal(p.run('translateBackend("Granskning klar")'), "Granskning klar");
});
test("all Swedish static UI text and attributes have English translations", () => {
  const p = panel(), html = fs.readFileSync(path.join(staticDir,"index.html"), "utf8");
  const text = [...html.matchAll(/>([^<>]+)</g)].map(m=>m[1].trim());
  const attrs = [...html.matchAll(/(?:placeholder|aria-label)="([^"]+)"/g)].map(m=>m[1]);
  for (const value of [...text,...attrs].filter(s => /[åäöÅÄÖ]/.test(s))) {
    p.context.value = value;
    assert.equal(p.run("translations.has(value)"), true, value);
  }
});
