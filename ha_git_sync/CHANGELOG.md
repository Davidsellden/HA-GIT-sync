# Changelog

## 0.5.0

- Swedish/English panel with automatic HA profile language detection and a remembered browser override.
- Save-before-preview prompt for unsaved file selections, extra paths and exclusions; canceling or a failed save stops sync.
- English instructions with explicit Supervisor/platform requirements and GitHub initialization steps.
- Removed installation-specific dashboard default inference; explicit persisted settings remain intact.
- Fixed import/recovery of selected disk dashboard files when API dashboard sync is disabled.
- Frontend regression tests for language behavior and file selection prompts.

## 0.4.1

- Standalone source repository with neutral destination and commit identity defaults.
- Installation and update documentation.

## 0.4.0

- File/folder picker, search, custom exclusions and extra paths.
- Persistent scope shared by push/import; deselected files are preserved.
- Folder selections include future eligible files; protected entries cannot be selected.
- Scope changes invalidate previews; recovery supports a previous scope.

## 0.3.0

- Dashboard picker and configurable YAML destination under dashboards/.
- Persistent panel settings; dashboard changes invalidate previews.
- Recovery uses the original operation's dashboard mapping.

## 0.2.0

- Branch lists, explicit new branches and bounded file diffs.
- Local files missing from the source branch are preserved unless deletion is enabled.
- Configurable snapshot retention and staged file validation.
- Administrator ingress panel.

## 0.1.0

- Ingress panel with preview and separate push/import flows.
- Dedicated SSH key, verified GitHub host key and concurrent-push protection.
- HA backup, validation, persistent recovery journal and optional dashboard API sync.
