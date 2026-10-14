# Changelog

## 0.4.1

- Fristående kodrepo med neutrala GitHub- och e-postinställningar.
- Installation och uppdatering dokumenterade för det nya repot.

## 0.4.0

- Fil- och mappväljare med kryssrutor, sökning, egna undantag och extra sökvägar.
- Egna rotfiler som huset.yaml kan väljas utan kodändring.
- Sparat urval gäller åt båda håll; bortvalda filer bevaras i GitHub och HA.
- Mappval omfattar framtida tillåtna filer. Skyddade filer visas nedtonade.
- Urvalet bevaras vid omstart och invaliderar tidigare förhandsgranskningar.
- Återställning fungerar även efter att urvalet ändrats; JSON-hemligheter kontrolleras.

## 0.3.0

- Dashboardrullista och valfri YAML-sökväg under dashboards/ i Git-repot.
- Dashboardval sparas direkt i panelen och bevaras vid omstart.
- Neutral standard för nya installationer; befintlig hemma.yaml-koppling migreras utan filändring.
- Gamla förhandsgranskningar ogiltigförklaras när dashboardval ändras.
- Återställning använder dashboarden från den ursprungliga uppdateringen.

## 0.2.0

- Tydliga branchrullistor och separat val för ny push-branch.
- Läsbara, begränsade filskillnader i förhandsgranskningen; misstänkta hemligheter döljs.
- Lokala filer som saknas i målbranchen bevaras som standard; borttagningar måste väljas.
- Konfigurerbar retention för lokala snapshots (standard: tre), med aktiv återställningspunkt skyddad.
- Git index verifieras mot den godkända fillistan innan commit.
- Adminpanel och dokumenterad jämförelse med andra Git-lösningar.

## 0.1.0

- Ingress-panel med granskning, branchval och separata push-/inläsningsflöden.
- Egen SSH-nyckel, verifierad GitHub-hostnyckel och skydd mot samtidiga Git-pushar.
- HA-backup, konfigurationskontroll, beständig journal och återställning.
- Valfri export/import av storage-dashboard via HA:s WebSocket-API.
