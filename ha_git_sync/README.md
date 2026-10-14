# HA Git Sync

Två flöden i en HA-panel: **Pusha till GitHub** och **Läs in från GitHub**.
Varje operation börjar med en förhandsgranskning av nya, ändrade och borttagna filer.

Det här är ett lokalt Home Assistant OS-tillägg för amd64/aarch64. Det kör Git i en
egen arbetskopia och kommer aldrig åt Proxmox-värden. Det kräver skrivåtkomst till
HA:s konfiguration och Supervisor-adminåtkomst för backup, kontroll och omstart.

## Installation

För ett publikt repo: öppna **Inställningar → Tillägg → Tilläggsbutik → ⋮ →
Repositories** och lägg till `https://github.com/Davidsellden/HA-GIT-sync`.
Installera sedan **HA Git Sync**. Repot är för närvarande privat; använd då lokal
installation enligt nedan.

### Lokal installation från ett privat repo

Klona repot i Advanced SSH & Web Terminal med ett GitHub-konto/SSH-nyckel som har
läsåtkomst. Kontrollera att `/addons` är HA:s monterade tilläggskatalog.

```sh
git clone git@github.com:Davidsellden/HA-GIT-sync.git /share/ha-git-sync-source
cp -R /share/ha-git-sync-source/ha_git_sync /addons/ha_git_sync
ha store reload
```

Om `/addons/ha_git_sync` redan finns, använd uppdateringsinstruktionen nedan.
Installera via **Tilläggsbutik → Lokala tillägg → HA Git Sync**.
Ange ditt eget `repository` som `ägare/repo` och din `git_email` i tilläggets
konfiguration **innan du startar det**. Aktivera **Visa i sidofältet** och öppna
webbgränssnittet. Ingen privat HA-konfiguration ingår i det här kodrepot.

### Anslut GitHub

1. Tryck **Skapa SSH-nyckel** i panelen.
2. Kopiera den publika nyckeln till repots **Settings → Deploy keys → Add deploy key**.
3. Välj **Allow write access** och spara.
4. Tryck **Testa anslutning**. Branchlistan hämtas.

Tillägget får en egen nyckel i `/data/ssh`. Det använder inte SSH-terminalens
privata nyckel. GitHubs Ed25519-hostnyckel kontrolleras mot dess publicerade
fingeravtryck innan den accepteras. Nyckeln skickas aldrig till Git-repot.

## Konfiguration

```yaml
repository: ditt-anvandarnamn/ditt-ha-repo
default_branch: main
push_branch: ha/updates
git_name: Home Assistant
git_email: homeassistant@example.com
dashboard_sync: false
dashboard_url_path: lovelace
dashboard_file: dashboards/overview.yaml
snapshot_retention: 3
```

`default_branch` är källbranch när en ny push-branch skapas. `push_branch` är
panelens förval; du kan välja en annan branch, inklusive `main`, uttryckligen.
Restart krävs när tilläggets alternativ ändras.

### Dashboard som redigeras i HA:s gränssnitt

I panelen, välj **Hämta dashboarder** och välj dashboard i rullistan. Ange en egen
Git-fil, exempelvis `dashboards/overview.yaml`, `dashboards/kitchen.yaml` eller
`dashboards/rooms/upstairs.yml`. Aktivera synkning och välj **Spara dashboardval**.
Det behövs ingen omstart och inga konfigurationsfiler i HA ändras av detta val.
Panelens sparade dashboardval har företräde framför tilläggets dashboardalternativ.

Tillägget exporterar den valda dashboarden till din valda Git-fil vid push.
Vid inläsning används HA:s `lovelace/config/save`-API. Dashboarden måste redan
finnas och vara redigerbar i storage-läge; tillägget skapar inte dashboarder och
skriver inte direkt i `.storage`. Dashboardresurser/HACS-kort synkas inte.

Om dashboard-synkning är avstängd lämnas dashboarden och GitHub-filen orörda.
Nya installationer föreslår `dashboards/dashboard.yaml`. Vid uppgradering av en
befintlig installation bevaras den tidigare `dashboards/hemma.yaml`-kopplingen
om ingen explicit fil valts. Ingen fil flyttas eller döps om automatiskt.
Synkning omfattar en vald dashboard; flera samtidiga dashboardkopplingar ingår
inte ännu. YAML-dashboarder som HA läser från disk visas inte som redigerbara val.

## Pusha

### Välj egna filer och mappar

I panelen: **Visa mina filer och mappar**. Bocka i exempelvis `huset.yaml` eller
en hel mapp, och välj **Spara filurval**. Mappval omfattar även nya tillåtna filer
som senare läggs i mappen. Filer som ingår via ett mappval visas markerade och
kan inte ändras separat; välj bort mappen för att välja dess filer enskilt, eller
ange en specifik fil under **Egna undantag**.

Du kan söka bland filerna. Skyddade poster visas nedtonade och deras innehåll
listas inte. **Extra sökvägar** kan användas för filer som ännu bara finns i
GitHub. Ange en sökväg per rad relativt `/config`, och avsluta mappnamn med `/`.
Inga globmönster eller absoluta sökvägar används.

Urvalet gäller både push och inläsning och sparas i tilläggets beständiga data.
Att välja bort en fil raderar den inte från HA eller GitHub; den slutar bara
hanteras av tillägget. Gamla förhandsgranskningar måste göras om efter ett ändrat
urval. HA:s aktiva konfiguration kontrolleras även om bara några filer valts.
Om `configuration.yaml` är vald måste den finnas på den sida som läses in.

Din gamla fasta fillista bevaras tills du sparar ett eget urval. Vid sparat
mappval hanteras alla tillåtna filtyper i den mappen, med skyddade undantag.
Dashboard-synkningen via API är separat; dess valda Git-fil hämtas från dashboarden
även om en vanlig fil med samma namn finns i `/config`.

1. Välj målbranch i rullistan, helst `ha/updates` under första testerna. Om den
   saknas, välj **Skapa ny branch** och ange namnet.
2. Skriv commit-meddelande och välj **Granska och pusha**.
3. Granska filnamnen, särskilt borttagningar, och bekräfta.

HA:s nuvarande konfiguration kontrolleras före commit. En branch som inte finns
skapas från `default_branch`. Git avvisar push om branchen har ändrats på GitHub
sedan förhandsgranskningen; inget skrivs då över. Dokumentation, tester och
tilläggskod bevaras. Vid oförändrat innehåll skapas ingen commit. YAML-radslut
normaliseras till LF i Git-kopian; enbart olika radslut ger inga falska ändringar.
Betydelsefulla avslutande radbrytningar i YAML-block bevaras.

## Läs in

1. Välj branch i rullistan och välj **Granska och läs in**. Branchlistan kan
   hämtas på nytt med **Uppdatera branchlistan**.
2. Öppna filernas diffar för att granska innehållet. Lokala filer som saknas i
   branchen bevaras som standard. Om du vill radera dem, markera **Ta även bort
   lokala filer som saknas i branchen** före granskningen. **Filer markerade
   ”tas bort” raderas från HA.**
3. Välj **Säkerhetskopiera och läs in**.

Förhandsgranskningen gäller i 15 minuter och låser uppdateringen till en bestämd
commit. Om HA-filer eller dashboard ändras före applicering stoppas operationen.
Undvik samtidiga redigeringar under själva uppdateringen; tillägget kan inte låsa
HA:s andra redigerare eller automation editor.

Tillägget kontrollerar först nuvarande konfiguration, skapar en **HA-backup** och
inväntar att Supervisor returnerar en färdig backup med HA-innehåll. Backupen
omfattar HA inklusive `.storage`, secrets och databasen; **andra tillägg och
Proxmox-VM:n ingår inte**. Den ska inte förväxlas med en fullständig systembackup.
Backupen hanteras i HA:s backupvy och tas inte bort automatiskt av detta tillägg.

Efter backupen sparas originalfilerna i tilläggets `/data/snapshots` och en
beständig journal skrivs innan HA-filerna ändras. Varje fil byts atomiskt, men hela
uppdateringen är inte en enda atomisk filsystemsoperation. Därefter körs
Supervisor `/core/check`, motsvarande `ha core check`. Vid godkänd kontroll
uppdateras eventuell dashboard via API. Ingen automatisk omstart sker.

Tryck **Kontrollera och starta om HA** för att aktivera filändringarna. Dashboarden
aktiveras direkt vid API-sparning. HA behöver köras på samma version som
konfigurationen är avsedd för; kontrollerna simulerar inte uppgraderingar av HA.

### Om något går fel

- Misslyckad backup: inga aktiva filer ändras.
- Ogiltig YAML: stoppas före backup. Fel vid HA-kontroll efter kopiering eller
  dashboardimport: originalfiler och eventuell dashboard återställs.
- Avbrott i tillägget under uppdatering: journalen upptäcks efter omstart, ny
  synkning blockeras och **Återställ senaste uppdateringen** kan användas.
- Manuell återställning skriver över senare ändringar i de berörda filerna och
  dashboarden. Panelen påminner om detta före återställningen.
- Om Core inte fungerar kan tillägget fortfarande återställa filerna, men
  dashboardens API och konfigurationskontrollen kan vara otillgängliga. Återstarta
  Core via Supervisor/terminal vid behov, eller återställ HA-backupen. Vid Core-fel
  kan ingresspanelen också vara otillgänglig; då används HA:s återställningsväg.

Återställning startar inte om Core automatiskt. Avinstallera inte tillägget eller
radera dess data innan en återställning är klar. `snapshot_retention` styr hur
många lokala snapshots som bevaras (1–20, standard tre). Aktiv återställningspunkt
skyddas alltid. Supervisor-backuper städas inte av tillägget.

## Uppdatera en lokal installation

Stoppa tillägget via HA. Följande kommandon ersätter bara tilläggskoden, inte
HA:s YAML, tilläggets inställningar eller dess beständiga data/SSH-nyckel:

```sh
git -C /share/ha-git-sync-source pull --ff-only origin main
cp -R /share/ha-git-sync-source/ha_git_sync/. /addons/ha_git_sync/
ha store reload
```

Välj **Uppdatera** om HA erbjuder version 0.4.1, annars **Bygg om/Rebuild** för
det lokala tillägget, och starta det. Avinstallera inte tillägget för att uppdatera.
Om gamla textfält fortfarande visas: ladda om panelen/webbläsaren.

Se [kodjämförelsen](COMPARISON.md) för vad vi granskat i andra Git-lösningar.

## Fillista och begränsningar

Det sparade urvalet kan omfatta egna YAML/YML, JSON, text, Markdown, CSV, Python,
shellskript, Jinja-mallar, XML, INI/CONF, JavaScript/CSS, SVG, bilder och
webbtypsnitt. Tillåtna filer i valda mappar hanteras rekursivt.

Standardurvalet före ett eget sparat val är:

- `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`.
- `.yaml`/`.yml` under `packages/`, `themes/`, `blueprints/`.
- Egna `.svg`, `.css`, `.js`, bilder och webbtypsnitt under `www/`.
- Valfri API-synkning av en vald dashboard till en egen `.yaml`/`.yml`-fil under `dashboards/`.

Följande kan inte väljas, även via Extra sökvägar: `www/community`, dolda filer/kataloger, namn som innehåller `secret`, `.storage`,
databaser, certifikat, privata nycklar, `custom_components` och `zigbee2mqtt`
hanteras inte. `known_devices.yaml` och `ip_bans.yaml` är också skyddade. Symboliska länkar i hanterade sökvägar avvisas. Max 10 MB per fil
och totalt 64 MB hanterade konfigurationsfiler.

Filer utanför fillistan som redan finns i GitHub bevaras; undantagslistan tar inte
bort tidigare uppladdade hemligheter ur Git-historiken.

YAML kontrolleras utan att lösa `!secret` eller `!include`. En enkel sökning efter
känsliga nycklar och privata nyckelblock stoppar misstänkta filer och visar enbart
filnamn. Det är ingen garanti att alla hemligheter hittas: granska innehållet före
push och använd ett privat repo. GitHub-branchen bör vara betrodd eftersom
HA-konfiguration kan innehålla körbara kommandon.

Panelen är tillgänglig enbart via HA-ingress. Ingen extern port exponeras.
POST-anrop kräver panelens CSRF-token, och endast en operation får köras åt gången.

## Utveckling och tester

```sh
python -m pip install -r ha_git_sync/requirements.txt
python -m unittest discover -s ha_git_sync/tests -v
python -m unittest discover -s tests -v
python scripts/sync-theme-styles.py --check
docker build -t ha-git-sync:local ha_git_sync
```

Integrationstesterna kör riktig Git mot tillfälliga lokala repon och en simulerad
Supervisor/dashboard. Installation och API-behörigheter måste också provas i
den riktiga HA-VM:n innan tillägget används för ordinarie uppdateringar.
