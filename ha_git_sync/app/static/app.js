"use strict";
const $ = id => document.getElementById(id);
let csrf = "", plan = null, busy = false, initialized = false, defaults = null, branchesLoaded = false;
let fileCatalog = [], selectedPaths = new Set();
const NEW_BRANCH = "@{create}";
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Kunde inte nå tillägget.");
  return result;
}
function error(message) { $("error").textContent = message || ""; $("error").hidden = !message; }
function disable(value) {
  busy = value;
  for (const id of ["key","connect","confirm","cancel","restart","refresh","list-dashboards","push-branch","pull-branch","new-branch","allow-deletions","message","save-dashboard","dashboard-target","dashboard-file","dashboard-enabled","load-files","save-files","extra-paths","exclude-paths","file-search"]) $(id).disabled = value;
  for (const checkbox of document.querySelectorAll("#file-list input")) checkbox.disabled = value || checkbox.dataset.inherited === "1" || checkbox.dataset.blocked === "1";
  $("push").disabled = value || !branchesLoaded;
  $("pull").disabled = value || !branchesLoaded || !$("pull-branch").value;
  $("restore").disabled = value || !$("restore").dataset.available;
  $("badge").textContent = value ? "Arbetar" : "Redo";
}
async function status() {
  const state = await api("api/status"); csrf = state.csrf;
  $("phase").textContent = state.phase;
  $("repository").textContent = state.repository || "Home Assistant-konfiguration";
  $("keys-link").href = `https://github.com/${state.repository}/settings/keys`;
  $("setup").hidden = initialized;
  $("key").hidden = !!state.public_key;
  $("public-key").hidden = !state.public_key;
  $("copy-key").hidden = !state.public_key;
  if (state.public_key) $("public-key").value = state.public_key;
  if (!defaults) {
    defaults = {push:state.push_branch, pull:state.default_branch};
    $("new-branch").value = state.push_branch;
    $("branch-base").textContent = `Skapas från ${state.default_branch}.`;
  }
  $("dashboard").textContent = state.dashboard_sync ? `Aktivt val: ${state.dashboard_url_path} ↔ ${state.dashboard_file}.` : "Dashboard-synkning är avstängd. Välj dashboard, filnamn och spara för att aktivera den.";
  $("scope-summary").textContent = `Sparat urval: ${state.scope.includes.join(", ") || "inga filer"}${state.scope.excludes.length ? " · egna undantag: " + state.scope.excludes.join(", ") : ""}`;
  if (!$("dashboard-file").dataset.loaded) {
    $("dashboard-enabled").checked = state.dashboard_sync;
    $("dashboard-file").value = state.dashboard_file;
    if (![...$("dashboard-target").options].some(option => option.value === state.dashboard_url_path)) {
      const option = document.createElement("option"); option.value = state.dashboard_url_path; option.textContent = state.dashboard_url_path;
      $("dashboard-target").append(option);
    }
    $("dashboard-target").value = state.dashboard_url_path;
    $("dashboard-file").dataset.loaded = "1";
  }
  $("restore").dataset.available = state.rollback ? "1" : "";
  $("restore").disabled = busy || !state.rollback;
  $("rollback").textContent = state.rollback ? `Senaste återställningspunkt: ${state.rollback.branch}, ${state.rollback.commit.slice(0,8)}. Backup: ${state.rollback.backup}.` : "";
  if (state.last_result) {
    const r = state.last_result;
    $("result").textContent = `${r.operation}${r.branch ? " · " + r.branch : ""}${r.commit ? " · " + r.commit.slice(0,8) : ""}`;
  }
  return state;
}
async function job(action, fields={}) {
  error(""); disable(true);
  try {
    const started = await api("api/jobs", {action, ...fields});
    return await watchJob(started.id);
  } finally { disable(false); }
}
async function watchJob(id) {
  while (true) {
    await sleep(750);
    const [progress] = await Promise.all([api(`api/jobs/${id}`), status()]);
    if (progress.done) {
      if (progress.error) throw new Error(progress.error);
      return progress.result;
    }
  }
}
async function loadBranches() {
  invalidatePreview();
  const branches = await job("branches");
  const previous = {push:$("push-branch").value === NEW_BRANCH ? $("new-branch").value.trim() : $("push-branch").value, pull:$("pull-branch").value};
  for (const mode of ["push", "pull"]) {
    const options = branches.map(name => { const el = document.createElement("option"); el.value = name; el.textContent = name; return el; });
    if (mode === "push") { const el = document.createElement("option"); el.value = NEW_BRANCH; el.textContent = "＋ Skapa ny branch…"; options.push(el); }
    else if (!options.length) { const el = document.createElement("option"); el.value = ""; el.textContent = "Inga brancher hittades"; options.push(el); }
    $(mode + "-branch").replaceChildren(...options);
    const preferred = previous[mode] || defaults[mode];
    $(mode + "-branch").value = branches.includes(preferred) ? preferred : mode === "push" ? NEW_BRANCH : branches.includes(defaults.pull) ? defaults.pull : branches[0] || "";
  }
  branchesLoaded = true; updateNewBranch(); disable(false);
  initialized = true; $("setup").hidden = true;
}
function updateNewBranch() { $("new-branch-fields").hidden = $("push-branch").value !== NEW_BRANCH; }
function invalidatePreview() { plan = null; $("preview").hidden = true; }
function renderFiles() {
  const query = $("file-search").value.toLowerCase();
  $("file-list").replaceChildren(...fileCatalog.filter(entry => entry.path.toLowerCase().includes(query)).map(entry => {
    const row = document.createElement("label"), box = document.createElement("input"), name = document.createElement("span");
    const inherited = [...selectedPaths].some(rule => rule.endsWith("/") && rule !== entry.path && entry.path.startsWith(rule));
    const excluded = pathLines("exclude-paths").some(rule => rule.endsWith("/") ? entry.path.startsWith(rule) : entry.path === rule);
    row.className = "file-row" + (entry.blocked ? " blocked" : ""); box.type = "checkbox"; box.checked = !entry.blocked && !excluded && (selectedPaths.has(entry.path) || inherited);
    box.disabled = busy || inherited || entry.blocked; box.dataset.inherited = inherited ? "1" : "0"; box.dataset.blocked = entry.blocked ? "1" : "0";
    box.addEventListener("change", () => { if (box.checked) selectedPaths.add(entry.path); else selectedPaths.delete(entry.path); renderFiles(); invalidatePreview(); });
    name.textContent = `${entry.directory ? "Mapp: " : ""}${entry.path}${entry.blocked ? " · kan inte synkas" : excluded ? " · undantagen" : inherited ? " · ingår via mapp" : !entry.exists ? " · saknas lokalt" : ""}`;
    row.append(box,name); return row;
  }));
}
$("file-search").addEventListener("input", renderFiles);
$("exclude-paths").addEventListener("input", () => { renderFiles(); invalidatePreview(); });
const pathLines = id => $(id).value.split("\n").map(line => line.trim()).filter(Boolean);
bind("load-files", async () => {
  const result = await job("scope_catalog"); fileCatalog = result.entries; selectedPaths = new Set(result.includes);
  $("exclude-paths").value = result.excludes.join("\n"); $("extra-paths").value = "";
  $("file-picker").hidden = false; renderFiles();
});
bind("save-files", async () => {
  invalidatePreview();
  const result = await job("configure_scope", {includes:[...new Set([...selectedPaths, ...pathLines("extra-paths")])], excludes:pathLines("exclude-paths")});
  for (const path of result.includes) if (!fileCatalog.some(entry => entry.path === path)) fileCatalog.push({path, directory:path.endsWith("/"), exists:false, blocked:false});
  selectedPaths = new Set(result.includes); $("extra-paths").value = ""; $("exclude-paths").value = result.excludes.join("\n"); renderFiles();
  await status();
});
$("push-branch").addEventListener("change", () => { updateNewBranch(); invalidatePreview(); });
for (const id of ["pull-branch", "new-branch", "allow-deletions"]) $(id).addEventListener("change", invalidatePreview);
async function preview(mode) {
  plan = null; $("preview").hidden = true;
  const branch = mode === "push" && $("push-branch").value === NEW_BRANCH ? $("new-branch").value.trim() : $(mode + "-branch").value;
  const result = await job("preview_" + mode, {branch, allow_deletions:mode === "pull" && $("allow-deletions").checked});
  plan = result;
  $("preview-title").textContent = mode === "push" ? "HA → GitHub" : "GitHub → HA";
  $("preview-meta").textContent = `${result.branch} · ${result.commit.slice(0,8)}${result.new_branch ? " · ny branch" : ""}`;
  $("changes").replaceChildren(...result.changes.map(change => {
    const row = document.createElement("tr");
    for (const text of [change.path, change.action]) { const cell = document.createElement("td"); cell.textContent = text; row.append(cell); }
    return row;
  }));
  $("diffs").replaceChildren(...result.changes.map(change => {
    const detail = document.createElement("details"), summary = document.createElement("summary"), text = document.createElement("pre");
    summary.textContent = "Visa skillnad: " + change.path;
    text.textContent = change.diff || "Binär eller stor fil. Skillnaden visas enbart i fillistan.";
    detail.append(summary, text); return detail;
  }));
  $("preview-note").textContent = !result.changes.length ? result.new_branch ? "Skapar en ny branch utan nya filändringar." : "Inga ändringar behövs." : mode === "pull" ? "Filer markerade ”tas bort” raderas från HA. En backup och lokal återställningspunkt skapas före ändringen. Granskningen gäller i 15 minuter." : "Ändringarna sparas i vald GitHub-branch. Granskningen gäller i 15 minuter.";
  if (result.kept_local?.length) $("preview-note").textContent += ` ${result.kept_local.length} lokala filer som saknas i branchen bevaras.`;
  $("confirm").textContent = mode === "push" ? "Bekräfta push" : "Säkerhetskopiera och läs in";
  $("confirm").disabled = !result.changes.length && !result.new_branch;
  $("preview").hidden = false; $("preview").scrollIntoView({behavior:"smooth", block:"start"});
}
function bind(id, handler) { $(id).addEventListener("click", () => handler().catch(err => error(err.message))); }
bind("key", async () => { await job("setup_key"); await status(); });
bind("copy-key", async () => { try { await navigator.clipboard.writeText($("public-key").value); } catch { $("public-key").select(); throw new Error("Nyckeln är markerad. Kopiera den manuellt."); } });
bind("connect", loadBranches); bind("refresh", loadBranches);
bind("push", () => preview("push")); bind("pull", () => preview("pull"));
bind("confirm", async () => {
  if (!plan) return;
  const current = plan; plan = null; $("preview").hidden = true;
  const result = await job(current.mode, {plan_id:current.id, message:$("message").value});
  await status();
  if (result.backup) $("result").textContent += " · Backup " + result.backup;
});
bind("cancel", async () => { plan = null; $("preview").hidden = true; });
bind("restart", async () => { if (confirm("Kontrollera konfigurationen och starta om Home Assistant nu?")) await job("restart"); });
bind("restore", async () => { if (confirm("Återställ filerna från före senaste inläsningen? Senare ändringar i de berörda filerna och dashboarden skrivs över.")) { await job("restore"); await status(); } });
bind("list-dashboards", async () => {
  const result = await job("dashboards");
  const previous = $("dashboard-target").value;
  const dashboards = result.filter(d => d.mode === "storage");
  if (!result.some(d => d.url_path === "lovelace")) dashboards.unshift({title:"Standarddashboard", url_path:"lovelace"});
  $("dashboard-target").replaceChildren(...dashboards.map(d => { const el = document.createElement("option"); el.value = d.url_path; el.textContent = `${d.title} (${d.url_path})`; return el; }));
  if (dashboards.some(d => d.url_path === previous)) $("dashboard-target").value = previous;
  $("dashboard-list").textContent = dashboards.length ? "Listan visar dashboarder som redigeras i HA:s gränssnitt." : "Inga redigerbara dashboarder hittades.";
  $("dashboard-list").hidden = false;
});
bind("save-dashboard", async () => {
  invalidatePreview();
  await job("configure_dashboard", {enabled:$("dashboard-enabled").checked, url_path:$("dashboard-target").value, repo_file:$("dashboard-file").value.trim()});
  $("dashboard-file").dataset.loaded = "";
  await status();
});
disable(true);
status().then(async state => {
  disable(false);
  if (state.active_job) {
    disable(true);
    try { await watchJob(state.active_job.id); await status(); }
    finally { disable(false); }
    if (state.public_key) await loadBranches();
  } else if (state.public_key && !state.rollback?.phase?.includes("required")) await loadBranches();
}).catch(err => error(err.message));
