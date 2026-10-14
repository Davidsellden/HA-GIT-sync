# Kodgranskning av andra HA/Git-lösningar

Granskad 2026-10-14. Funktioner som beskrivs i dokumentation är skilda från
funktioner som har kontrollerats i tillgänglig källkod. Ingen kod har kopierats.

| Projekt och granskad källa | Vad som fungerar väl | Bedömning för vårt tillägg |
| --- | --- | --- |
| [ckrl/ha-gitops](https://github.com/ckrl/ha-gitops/blob/c92ea07ca61b6c37edca2c9055bac32e1481bb55/custom_components/ha_gitops/git_manager.py) | Fast-forward-only vid pull, separat fetch, kontroll av staged secrets och strukturerad Git-status. | Vår motor behåller isolerade arbetskopior och backup. Indexet verifieras nu uttryckligen mot godkända filnamn. Statussensorer är ett användbart framtida tillägg. |
| [askb/ha-gitops](https://github.com/askb/ha-gitops/blob/56bdb6461718f5fb79f2b458d31a306cc4612af7/gitops_backup/rootfs/app/gitops_backup.sh) | Separata backupbrancher, automatisk PR och valideringsmallar för CI. | Vi behåller en separat push-branch som standard. En länk för manuell PR räcker tills eventuell GitHub API-autentisering utformats. Skriptets automatiska konfliktval med stash/checkouts återanvänds inte; vårt flöde kräver granskning. |
| [a4ng3i/ha-apps](https://github.com/a4ng3i/ha-apps/tree/cb4db7776100b51859b7f21cc9bbe3b6c9ccf7bc/ha-git-sync) | Dokumenterar per-fil-policy, konflikter, diffgranskning, retention och förbud mot oavsiktlig radering av lokala filer. | Publika repot innehåller installationsmanifest, dokumentation och changelog, **inte synkmotorns källkod**. Idéerna har bedömts via dokumentation, inte bevisats genom kodgranskning. Vårt tillägg får fil-diffar, explicit borttagningsval och snapshotretention. |
| [Officiella Git pull](https://github.com/home-assistant/addons/blob/f9fa97ab7569ce5456e46684248187a411a75abc/git_pull/data/run.sh) | Litet, tydligt pull-flöde och HA-kontroll. | Kör Git i den aktiva konfigurationskatalogen och stöder hard reset. Vi behåller isolerad checkout, låst commit och återställningsjournal. |

## Förbättringar i 0.2.0

- Rullistor visar faktiska remote-brancher. En ny push-branch väljs uttryckligen.
- Läsbara fil-diffar ger bättre granskning än enbart filnamn. Diffar är begränsade
  i storlek och göms om de kan visa hemligheter, även hemligheter som tas bort.
- Lokala filer som saknas i pull-branchen bevaras som standard. Radering kräver
  ett separat val före granskning och omfattas av backup/återställning.
- Standardretention: tre lokala snapshots. Aktiv återställningspunkt bevaras
  alltid. HA/Supervisor-backuper omfattas inte av denna städning.
- Git index måste matcha den godkända ändringslistan innan commit.
- `panel_admin` är aktiverat. Aktuell [Supervisor-ingress](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/ingress.py)
  kontrollerar administratörsbehörigheten; tillägget kräver dessutom ingressens
  interna peer-adress och CSRF-token för ändrande anrop.

## Nästa utvecklingsområden

Trevägsjämförelse med en beständig basversion skulle kunna upptäcka ändringar
på båda sidor innan granskning. Det är inte samma sak som vårt nuvarande skydd
mot ändringar efter granskning eller samtidiga remote-pushar. Idag väljer
användaren riktning och godkänner de synliga skillnaderna; ingen automatisk
textmerge sker.

Andra kandidater är HA-statussensorer, domänspecifik omladdning och PR-länk efter
push. De behöver egna tester och ett tydligt användarflöde innan de införs.
