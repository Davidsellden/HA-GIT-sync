# HA Git Sync

Granska, säkerhetskopiera och synka valda Home Assistant-filer med ditt eget GitHub-repo.

- Välj filer och mappar med kryssrutor.
- Välj branch för push eller import.
- Synka en dashboard via HA:s API.
- Granska ändringar, ta HA-backup och kontrollera konfigurationen före import.
- Återställ senaste import vid behov.

För Home Assistant OS/Supervised med Supervisor, amd64 eller aarch64.

[Installation, konfiguration och uppdatering](ha_git_sync/README.md) ·
[Ändringslogg](ha_git_sync/CHANGELOG.md) · [Jämförelse med andra lösningar](ha_git_sync/COMPARISON.md)

Kodrepot innehåller inga personliga HA-filer. Ange ditt eget målrepo i tilläggets
konfiguration före första starten. Detta repo är för närvarande privat.
