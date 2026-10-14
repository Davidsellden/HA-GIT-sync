# HA Git Sync

Review, back up and sync selected Home Assistant files with your own GitHub repository.

- Select individual files or folders and preview changes before push/import.
- Save unsaved file selections before continuing a sync.
- Create an HA backup before import and restore the last update if needed.
- Optionally sync one dashboard through the HA API.
- Automatically use Swedish for a Swedish HA profile, otherwise English; override the language in the panel.

**Requirements:** Home Assistant OS with Supervisor, amd64 or aarch64, and an initialized GitHub repository. Existing Supervised installations with a working Supervisor may also run the add-on. Container and standalone Core are not supported.

[Installation and usage](ha_git_sync/DOCS.md) · [Changelog](ha_git_sync/CHANGELOG.md) · [Design notes](ha_git_sync/COMPARISON.md)

This project contains add-on code and synthetic tests, with no bundled HA configuration, credentials, private instance addresses or preconfigured sync destination. Metadata URLs identify this project's source repository. Configure your own destination before starting.
