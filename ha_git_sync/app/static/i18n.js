"use strict";
const translations = new Map();
let language = "en";
let languagePreference = "auto";
try { languagePreference = localStorage.getItem("ha-git-sync-language") || "auto"; } catch {}
function haLanguage() {
  try {
    let frame = window;
    while (frame !== frame.parent) {
      frame = frame.parent;
      const host = frame.document.querySelector("home-assistant");
      if (host?.hass?.language) return host.hass.language;
    }
    return "en";
  } catch { return "en"; }
}
function resolveLanguage() {
  const value = languagePreference === "auto" ? haLanguage() : languagePreference;
  return /^sv(?:-|$)/i.test(value) ? "sv" : "en";
}
function t(swedish, english) { return language === "sv" ? swedish : english; }
const translatedNodes = [];
function applyLanguage() {
  language = resolveLanguage();
  document.documentElement.lang = language;
  for (const {node, attribute, sv, en} of translatedNodes) {
    if (attribute) node.setAttribute(attribute, t(sv, en));
    else node.textContent = t(sv, en);
  }
}
function initializeLanguage() {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode, sv = node.textContent.trim();
    if (translations.has(sv)) translatedNodes.push({node, sv:node.textContent, en:node.textContent.replace(sv, translations.get(sv))});
  }
  for (const node of document.querySelectorAll("[placeholder], [aria-label]")) {
    for (const attribute of ["placeholder", "aria-label"]) {
      const sv = node.getAttribute(attribute);
      if (translations.has(sv)) translatedNodes.push({node, attribute, sv, en:translations.get(sv)});
    }
  }
  $("language").value = ["auto", "sv", "en"].includes(languagePreference) ? languagePreference : "auto";
  $("language").addEventListener("change", () => {
    languagePreference = $("language").value;
    try { localStorage.setItem("ha-git-sync-language", languagePreference); } catch {}
    refreshLanguage();
  });
  applyLanguage();
  setInterval(() => {
    if (!busy && resolveLanguage() !== language) {
      refreshLanguage();
    }
  }, 2000);
}
function refreshLanguage() {
  applyLanguage(); renderFiles(); invalidatePreview(); disable(busy);
  for (const option of $("push-branch").options) {
    if (option.value === NEW_BRANCH) option.textContent = t("＋ Skapa ny branch…", "＋ Create new branch…");
  }
  for (const option of $("pull-branch").options) {
    if (!option.value) option.textContent = t("Inga brancher hittades", "No branches found");
  }
  $("dashboard-list").hidden = true;
  status().catch(err => error(err.message));
}

translations.set("Din konfiguration, versionshanterad.", "Your configuration, version controlled.");
translations.set("Redo", "Ready");
translations.set("Ansluter till tillägget…", "Connecting to the add-on…");
translations.set("ANSLUT GITHUB", "CONNECT GITHUB");
translations.set("En egen nyckel för tillägget", "A dedicated key for this add-on");
translations.set("Skapa en SSH-nyckel och lägg den publika nyckeln som", "Create an SSH key and add the public key as a");
translations.set("med", "with");
translations.set("i ditt privata GitHub-repo.", "in your private GitHub repository.");
translations.set("Skapa SSH-nyckel", "Create SSH key");
translations.set("Publik SSH-nyckel", "Public SSH key");
translations.set("Kopiera nyckel", "Copy key");
translations.set("Öppna deploy keys ↗", "Open deploy keys ↗");
translations.set("Testa anslutning", "Test connection");
translations.set("Pusha till GitHub", "Push to GitHub");
translations.set("Spara de aktuella HA-filerna som en ny commit. Granska ändringarna först.", "Save the current HA files as a new commit. Review the changes first.");
translations.set("Branch att pusha till", "Branch to push to");
translations.set("Hämta branchlistan först", "Load the branch list first");
translations.set("Namn på ny branch", "New branch name");
translations.set("Commit-meddelande", "Commit message");
translations.set("Granska och pusha", "Review and push");
translations.set("Läs in från GitHub", "Import from GitHub");
translations.set("Ta en HA-backup, uppdatera filerna och kontrollera konfigurationen.", "Create an HA backup, update files and validate the configuration.");
translations.set("Branch att läsa in", "Branch to import");
translations.set("Ta även bort lokala filer som saknas i branchen", "Also delete local files missing from the branch");
translations.set("Inläsningen körs mot en bestämd commit. Om kontrollen misslyckas återställs originalen.", "Import uses a fixed commit. If validation fails, the originals are restored.");
translations.set("Granska och läs in", "Review and import");
translations.set("FÖRHANDSGRANSKNING", "PREVIEW");
translations.set("Fil", "File");
translations.set("Ändring", "Change");
translations.set("Bekräfta", "Confirm");
translations.set("Avbryt", "Cancel");
translations.set("EFTER EN UPPDATERING", "AFTER AN UPDATE");
translations.set("Aktivera eller återställ", "Activate or restore");
translations.set("En godkänd filuppdatering startar inte om HA automatiskt. Dashboardändringar aktiveras direkt via API:t.", "A validated file update does not restart HA automatically. Dashboard changes take effect immediately through the API.");
translations.set("Kontrollera och starta om HA", "Validate and restart HA");
translations.set("Återställ senaste uppdateringen", "Restore last update");
translations.set("DITT FILURVAL", "YOUR FILE SELECTION");
translations.set("Välj filer och mappar", "Select files and folders");
translations.set("Bocka i enstaka filer eller hela mappar. Ett mappval omfattar även framtida tillåtna filer. Samma urval används för push och inläsning.", "Select individual files or entire folders. Folder selections also include future eligible files. The same selection is used for push and import.");
translations.set("Visa mina filer och mappar", "Show my files and folders");
translations.set("Sök bland filer", "Search files");
translations.set("Exempel: custom.yaml", "Example: custom.yaml");
translations.set("Extra sökvägar, även filer som ännu bara finns i GitHub", "Extra paths, including files currently only in GitHub");
translations.set("Egna undantag, en fil eller mapp per rad", "Custom exclusions, one file or folder per line");
translations.set("Spara filurval", "Save file selection");
translations.set("Secrets, dolda kataloger, databaser, loggar, HACS och Zigbee2MQTT kan inte väljas. Mappar anges med / på slutet.", "Secrets, hidden directories, databases, logs, HACS and Zigbee2MQTT cannot be selected. Folder paths end with /.");
translations.set("VALFRI DASHBOARD", "OPTIONAL DASHBOARD");
translations.set("Välj dashboard och Git-fil", "Select dashboard and Git file");
translations.set("Synka en dashboard som du redigerar i Home Assistants gränssnitt. Du väljer själv filnamnet i GitHub.", "Sync a dashboard edited in the Home Assistant interface. Choose its file name in GitHub.");
translations.set("Synka den valda dashboarden", "Sync the selected dashboard");
translations.set("Dashboard i Home Assistant", "Dashboard in Home Assistant");
translations.set("Hämta dashboarder", "Load dashboards");
translations.set("YAML-fil i Git-repot", "YAML file in the Git repository");
translations.set("Välj ett eget filnamn under dashboards/. Vid push skapas filen om den saknas. Vid inläsning måste filen finnas i vald branch.", "Choose a file name under dashboards/. Push creates the file if missing. For import, the file must exist in the selected branch.");
translations.set("Spara dashboardval", "Save dashboard selection");
translations.set("Vad synkas?", "What is synced?");
translations.set("Ditt sparade filurval och eventuell vald dashboard. Filer utanför urvalet i GitHub bevaras.", "Your saved file selection and optional dashboard. Unselected files in GitHub are preserved.");
translations.set("Secrets, .storage, databaser, HACS-filer och Zigbee2MQTT ingår inte. Backupen omfattar Home Assistant, inklusive dess databas och interna inställningar, men inte andra tillägg.", "Secrets, .storage, databases, HACS files and Zigbee2MQTT are excluded. The backup includes Home Assistant, its database and internal settings, but excludes other add-ons.");
translations.set("Uppdatera branchlistan", "Refresh branches");
translations.set("Språk", "Language");
translations.set("Automatiskt (Home Assistant)", "Automatic (Home Assistant)");
translations.set("Kunde inte nå tillägget.", "Could not reach the add-on.");
translations.set("Arbetar", "Working");
translations.set("Home Assistant-konfiguration", "Home Assistant configuration");
translations.set("Dashboard-synkning är avstängd. Välj dashboard, filnamn och spara för att aktivera den.", "Dashboard sync is disabled. Select a dashboard and file name, then save to enable it.");
translations.set("inga filer", "no files");
translations.set(" · egna undantag: ", " · custom exclusions: ");
translations.set("＋ Skapa ny branch…", "＋ Create new branch…");
translations.set("Inga brancher hittades", "No branches found");
translations.set("Mapp: ", "Folder: ");
translations.set(" · kan inte synkas", " · cannot be synced");
translations.set(" · undantagen", " · excluded");
translations.set(" · ingår via mapp", " · included by folder");
translations.set(" · saknas lokalt", " · missing locally");
translations.set(" · ny branch", " · new branch");
translations.set("Visa skillnad: ", "Show diff: ");
translations.set("Binär eller stor fil. Skillnaden visas enbart i fillistan.", "Binary or large file. Changes are only shown in the file list.");
translations.set("Skapar en ny branch utan nya filändringar.", "Creates a new branch without file changes.");
translations.set("Inga ändringar behövs.", "No changes needed.");
translations.set("Filer markerade ”tas bort” raderas från HA. En backup och lokal återställningspunkt skapas före ändringen. Granskningen gäller i 15 minuter.", "Files marked “deleted” are removed from HA. A backup and local recovery point are created first. The preview is valid for 15 minutes.");
translations.set("Ändringarna sparas i vald GitHub-branch. Granskningen gäller i 15 minuter.", "Changes are saved to the selected GitHub branch. The preview is valid for 15 minutes.");
translations.set("Bekräfta push", "Confirm push");
translations.set("Säkerhetskopiera och läs in", "Back up and import");
translations.set("Nyckeln är markerad. Kopiera den manuellt.", "The key is selected. Copy it manually.");
translations.set("Kontrollera konfigurationen och starta om Home Assistant nu?", "Validate the configuration and restart Home Assistant now?");
translations.set("Återställ filerna från före senaste inläsningen? Senare ändringar i de berörda filerna och dashboarden skrivs över.", "Restore files from before the last import? Later changes to those files and the dashboard will be overwritten.");
translations.set("Standarddashboard", "Default dashboard");
translations.set("Listan visar dashboarder som redigeras i HA:s gränssnitt.", "The list shows dashboards edited in the HA interface.");
translations.set("Inga redigerbara dashboarder hittades.", "No editable dashboards found.");

translations.set("Supervisor-token saknas. Kör tjänsten som ett HA-tillägg.", "Supervisor token missing. Run this service as an HA add-on.");
translations.set("Supervisor-token saknas.", "Supervisor token missing.");
translations.set("Backupen är inte bekräftat klar. Uppdateringen stoppades.", "Backup completion could not be verified. Update stopped.");
translations.set("Backupen innehåller inte Home Assistant. Uppdateringen stoppades.", "The backup does not contain Home Assistant. Update stopped.");
translations.set("Oväntat svar från HA:s dashboard-API.", "Unexpected response from the HA dashboard API.");
translations.set("Dashboard-API:t nekade åtkomst.", "The dashboard API denied access.");
translations.set("Dashboard-API:t kunde inte utföra kommandot. Kontrollera vald dashboard.", "The dashboard API could not execute the command. Check the selected dashboard.");
translations.set("Kunde inte nå HA:s dashboard-API.", "Could not reach the HA dashboard API.");
translations.set("Välj högst 200 filsökvägar eller mappar.", "Select up to 200 file paths or folders.");
translations.set("En vald sökväg är skyddad eller inte en tillåten konfigurationsfil.", "A selected path is protected or is not an eligible configuration file.");
translations.set("Ogiltig filsökväg.", "Invalid file path.");
translations.set("Filsökvägen ligger utanför konfigurationskatalogen.", "The file path is outside the configuration directory.");
translations.set("De valda filerna överstiger 64 MB.", "The selected files exceed 64 MB.");
translations.set("ny", "new");
translations.set("tas bort", "deleted");
translations.set("ändrad", "modified");
translations.set("Skillnaden döljs eftersom filen kan innehålla hemligheter. Granska lokalt.", "Diff hidden because the file may contain secrets. Review locally.");
translations.set("Skillnaden kan inte visas säkert. Granska filen lokalt.", "The diff cannot be displayed safely. Review the file locally.");
translations.set("Okänd YAML-tagg.", "Unknown YAML tag.");
translations.set("YAML innehåller dubbla nycklar.", "YAML contains duplicate keys.");
translations.set("configuration.yaml måste innehålla en YAML-mappning.", "configuration.yaml must contain a YAML mapping.");
translations.set("Packages måste innehålla YAML-mappningar.", "Packages must contain YAML mappings.");
translations.set("Dashboardens YAML är ogiltig.", "Invalid dashboard YAML.");
translations.set("Öppna panelen via Home Assistants ingress.", "Open this panel through Home Assistant ingress.");
translations.set("Panelen behöver laddas om.", "Reload the panel.");
translations.set("JSON krävs.", "JSON is required.");
translations.set("Operationen hittades inte. Ladda om panelen och kontrollera status.", "Operation not found. Reload the panel and check its status.");
translations.set("Ogiltig begäran.", "Invalid request.");
translations.set("Okänd operation.", "Unknown operation.");
translations.set("En operation pågår redan.", "An operation is already running.");
translations.set("Oväntat fel. Kontrollera återställningsstatus.", "Unexpected error. Check recovery status.");
translations.set("Filurvalet kan inte läsas. Kontrollera tilläggets data.", "Cannot read the file selection. Check the add-on data.");
translations.set("Dashboardinställningarna kan inte läsas. Kontrollera tilläggets data.", "Cannot read dashboard settings. Check the add-on data.");
translations.set("Ange GitHub-repot som ägare/repo.", "Enter the GitHub repository as owner/repo.");
translations.set("En avbruten uppdatering behöver återställas innan nästa synkning.", "An interrupted update must be restored before syncing again.");
translations.set("Återställning krävs", "Recovery required");
translations.set("En annan operation pågår. Vänta tills den är klar.", "Another operation is running. Wait until it finishes.");
translations.set("Återställ den avbrutna uppdateringen först.", "Restore the interrupted update first.");
translations.set("Oväntat fel. Kontrollera tilläggets logg och återställningsstatus.", "Unexpected error. Check the add-on log and recovery status.");
translations.set("Stoppad", "Stopped");
translations.set("Git/SSH kunde inte slutföra operationen. Kontrollera åtkomst och nätverk.", "Git/SSH could not complete the operation. Check access and network connectivity.");
translations.set("Git/SSH nekade operationen. Kontrollera deploy key, branch och eventuella Git-konflikter.", "Git/SSH rejected the operation. Check the deploy key, branch and Git conflicts.");
translations.set("SSH-nyckeln är redo", "SSH key ready");
translations.set("Skapa SSH-nyckeln och lägg till den som deploy key i GitHub först.", "Create the SSH key and add it as a GitHub deploy key first.");
translations.set("GitHubs SSH-fingeravtryck stämmer inte. Anslutningen stoppades.", "GitHub SSH fingerprint mismatch. Connection stopped.");
translations.set("Hämtar GitHub-brancher", "Loading GitHub branches");
translations.set("GitHub anslutet", "Connected to GitHub");
translations.set("Ogiltigt branchnamn.", "Invalid branch name.");
translations.set("Dashboardfilen måste vara en säker, relativ YAML-sökväg under dashboards/.", "The dashboard file must be a safe relative YAML path under dashboards/.");
translations.set("Välj en giltig dashboard och synkningsinställning.", "Select a valid dashboard and sync setting.");
translations.set("Dashboarden finns inte. Hämta dashboardlistan på nytt.", "Dashboard not found. Reload the dashboard list.");
translations.set("Välj en dashboard som redigeras i HA:s gränssnitt.", "Select a dashboard edited in the HA interface.");
translations.set("Dashboardinställningarna sparade", "Dashboard settings saved");
translations.set("Filurvalet sparat", "File selection saved");
translations.set("För många filer att visa. Använd extra sökvägar eller mindre mappar i filurvalet.", "Too many files to display. Use extra paths or smaller folders in your selection.");
translations.set("Filurvalet hämtat", "File selection loaded");
translations.set("Den valda branchen finns inte på GitHub.", "The selected branch does not exist on GitHub.");
translations.set("Basbranchen finns inte på GitHub.", "The base branch does not exist on GitHub.");
translations.set("Ogiltig operation.", "Invalid operation.");
translations.set("Ogiltigt val för borttagningar.", "Invalid deletion setting.");
translations.set("Den valda dashboarden är inte redigerbar i storage-läge.", "The selected dashboard is not editable in storage mode.");
translations.set("configuration.yaml saknas i branchen. Uppdateringen stoppades.", "configuration.yaml is missing from the branch. Update stopped.");
translations.set("configuration.yaml saknas. Uppdateringen stoppades.", "configuration.yaml is missing. Update stopped.");
translations.set("Granskning klar", "Preview ready");
translations.set("Förhandsgranskningen har gått ut. Granska på nytt.", "The preview has expired. Review again.");
translations.set("HA-filer eller dashboard ändrades efter granskningen. Granska på nytt.", "HA files or dashboard changed after previewing. Review again.");
translations.set("Ange ett commit-meddelande på högst 500 tecken.", "Enter a commit message of up to 500 characters.");
translations.set("Branchen skapad", "Branch created");
translations.set("Inga ändringar att pusha", "No changes to push");
translations.set("Kontrollerar HA-konfigurationen", "Validating HA configuration");
translations.set("HA ändrades under kontrollen. Granska på nytt.", "HA changed during validation. Review again.");
translations.set("Git index stämmer inte med granskningen. Kontrollera repots ignore-regler och granska på nytt.", "The Git index does not match the preview. Check repository ignore rules and review again.");
translations.set("Pushar till GitHub", "Pushing to GitHub");
translations.set("Push klar", "Push complete");
translations.set("Återställningsjournalen kan inte läsas. Bevara /data och kontrollera loggen.", "Cannot read the recovery journal. Preserve /data and check the log.");
translations.set("HA stämmer redan med branchen", "HA already matches the branch");
translations.set("Kontrollerar nuvarande HA-konfiguration", "Validating current HA configuration");
translations.set("Tar backup av Home Assistant; inväntar färdig backup", "Backing up Home Assistant; waiting for completion");
translations.set("HA ändrades under backupen. Inga filer uppdaterades. Granska på nytt.", "HA changed during backup. No files were updated. Review again.");
translations.set("HA ändrades under förberedelsen. Inga filer uppdaterades. Granska på nytt.", "HA changed during preparation. No files were updated. Review again.");
translations.set("Läser in filer från GitHub", "Importing files from GitHub");
translations.set("Kontrollerar uppdaterad HA-konfiguration", "Validating updated HA configuration");
translations.set("Uppdaterar dashboard via HA:s API", "Updating dashboard through the HA API");
translations.set("Inläsning klar. Starta om HA när du är redo.", "Import complete. Restart HA when ready.");
translations.set("Uppdateringen misslyckades. Återställer originalen.", "Update failed. Restoring originals.");
translations.set("Uppdateringen och återställningen misslyckades. Använd Återställ eller HA-backupen.", "Update and recovery failed. Use Restore or the HA backup.");
translations.set("Uppdateringen misslyckades. Originalfiler och dashboard har återställts.", "Update failed. Original files and dashboard have been restored.");
translations.set("Ogiltig återställningskatalog.", "Invalid recovery directory.");
translations.set("Journalen innehåller en fil utanför fillistan.", "The journal contains a file outside the eligible file list.");
translations.set("Ingen uppdatering finns att återställa.", "No update available to restore.");
translations.set("Återställer senaste uppdateringen", "Restoring last update");
translations.set("Återställningen är inte klar. Originalen finns kvar; använd HA-backupen om Core inte går att kontrollera.", "Recovery is incomplete. Originals are preserved; use the HA backup if Core cannot be validated.");
translations.set("Återställd. Starta om HA för att aktivera originalkonfigurationen.", "Restored. Restart HA to activate the original configuration.");
translations.set("Kontrollerar och startar om Home Assistant", "Validating and restarting Home Assistant");
translations.set("Home Assistant startas om", "Home Assistant is restarting");

// Only fixed messages are translated; filenames, repository names and diffs are preserved.
function translateBackend(message) {
  if (!message || language === "sv") return message;
  if (translations.has(message)) return translations.get(message);
  const patterns = [
    [/^HA kunde inte slutföra (.+)\. Kontrollera Supervisor-loggen\.$/, "HA could not complete $1. Check the Supervisor log."],
    [/^Ingen godkänd respons från HA för (.+)\. Inga fler steg körs\.$/, "No valid response from HA for $1. No further steps will run."],
    [/^Symbolisk länk tillåts inte: (.+)$/, "Symbolic links are not allowed: $1"],
    [/^Förväntade en katalog: (.+)$/, "Expected a directory: $1"],
    [/^Filen är inte en vanlig fil eller överstiger 10 MB: (.+)$/, "File is not a regular file or exceeds 10 MB: $1"],
    [/^Ogiltig YAML: (.+)\. Kontrollera filen lokalt\.$/, "Invalid YAML: $1. Check the file locally."],
    [/^Ogiltig JSON: (.+)\. Granska filen lokalt\.$/, "Invalid JSON: $1. Review the file locally."],
    [/^Branchen saknar (.+)\.$/, "The branch is missing $1."],
    [/^Misstänkta hemligheter i: (.+)\. Flytta dem till secrets innan synkning\.$/, "Suspected secrets in: $1. Move them to secrets before syncing."]
  ];
  for (const [pattern, replacement] of patterns) if (pattern.test(message)) return message.replace(pattern, replacement);
  return message;
}
translations.set("Ange en YAML-fil under dashboards/, exempelvis dashboards/overview.yaml.", "Enter a YAML file under dashboards/, for example dashboards/overview.yaml.");
translations.set("Ogiltigt branchnamn.", "Invalid branch name.");
