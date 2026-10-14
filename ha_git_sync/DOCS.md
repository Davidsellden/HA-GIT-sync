# HA Git Sync

Sync selected Home Assistant files with **your own GitHub repository**, with a preview before every push or import. Git runs in an isolated working copy outside the active HA configuration.

## Requirements

- Home Assistant OS with Supervisor on `amd64` or `aarch64`, an administrator account and access to the add-on store.
- A GitHub repository you can manage. Use a private repository for HA configuration.
- At least one commit on its base branch. Select **Add a README file** when creating it.
- Outbound GitHub SSH access (port 22) and internet access for building the add-on.

Existing Supervised installations may work if their Supervisor provides add-on, backup and Core APIs. Container and standalone Core lack these services and are not supported. No particular hostname, instance IP, VM platform, dashboard name or personal configuration is required.

## Installation

1. In HA, open **Settings → Add-ons → Add-on store** (called **Apps** in newer versions).
2. Open **⋮ → Repositories**, add `https://github.com/Davidsellden/HA-GIT-sync`, then refresh the store.
3. Find **HA Git Sync** and select **Install**. The first build can take several minutes.
4. Before starting, open **Configuration** and set `repository` to **your configuration repository** in `owner/repo` form. Do not enter a URL or `.git` suffix. Set `default_branch` to its existing base branch, usually `main`.
5. Save, start the add-on, enable **Show in sidebar** if desired and open its web interface.
6. Complete the GitHub connection below.

The source repository must be public for other users to add it directly to the store. If private or inaccessible, an authorized user can install a local copy. The source and your configuration destination are separate repositories.

### Local installation

Copy this project's `ha_git_sync` directory into HA's `/addons/ha_git_sync`. In an HA terminal with Git and access to `/addons`, for example:

```sh
git clone https://github.com/Davidsellden/HA-GIT-sync.git /share/ha-git-sync-source
cp -R /share/ha-git-sync-source/ha_git_sync /addons/ha_git_sync
ha store reload
```

For private source access, use a separately authorized GitHub clone method. Terminal credentials are not used by the add-on. If the destination directory already exists, use the update instructions instead. Install via **Local add-ons → HA Git Sync**, configure your destination, then start.

## Connect GitHub

1. Select **Create SSH key** in the panel.
2. Select **Copy key**, then **Open deploy keys**, or visit your destination repository's **Settings → Deploy keys → Add deploy key**.
3. Paste the public key, give it a descriptive title, enable **Allow write access** and save.
4. Return to the panel and select **Test connection**. The branch list should load.

Each installation generates its own key. The private key stays in persistent `/data/ssh` and is never committed. GitHub's host key is verified against its published Ed25519 fingerprint. A deploy key grants access only to the repository where you add it.

## Configuration

```yaml
repository: your-account/your-ha-config
default_branch: main
push_branch: ha/updates
git_name: Home Assistant
git_email: homeassistant@example.com
dashboard_sync: false
dashboard_url_path: lovelace
dashboard_file: dashboards/dashboard.yaml
snapshot_retention: 3
```

| Option | Meaning |
| --- | --- |
| `repository` | Required destination GitHub repository, `owner/repo`. |
| `default_branch` | Existing base branch for new push branches. |
| `push_branch` | Suggested destination branch; change it in the panel. |
| `git_name`, `git_email` | Commit author identity. Set your own identity if desired. |
| `dashboard_sync` | Optional dashboard export/import, off by default. |
| `dashboard_url_path` | Dashboard URL path; `lovelace` means the default dashboard. |
| `dashboard_file` | Relative YAML path under `dashboards/`; empty uses `dashboards/dashboard.yaml`. |
| `snapshot_retention` | Local snapshots retained, 1–20; the active recovery point is protected. |

Restart after changing add-on options. File selections and dashboard settings saved in the panel persist immediately. Panel-saved dashboard settings override add-on options. Explicitly saved filenames remain intact; new installations never infer a personal dashboard filename.

## Language

The panel defaults to **Automatic (Home Assistant)** and reads the current user's HA frontend language. Swedish (`sv`) uses Swedish; all other languages use English. If HA's language is unavailable, English is used. An open panel follows changes to the HA language.

Choose **Language → Svenska / English / Automatic (Home Assistant)** to override or restore automatic selection. The choice is remembered in this browser. Changing language closes an existing preview; review again before syncing. This guide is in English.

## Select files and folders

1. Select **Show my files and folders**.
2. Select individual files or entire folders. Folders include future eligible files.
3. Optionally add **Extra paths** for files currently only in GitHub or **Custom exclusions** for files/folders to skip.
4. Select **Save file selection**.

Enter one path per line relative to `/config`; end folder paths with `/`. Absolute paths and glob patterns are unsupported. Files inherited from a selected folder are checked automatically. Exclude a file explicitly or deselect its parent folder to select files individually.

The saved scope applies to both push and import. Deselecting a file does not delete it on either side. Unsaved checkbox, extra-path or exclusion changes trigger a **save-before-preview** question at the next push or import. Confirming saves first; canceling returns to editing without syncing. A failed save stops the operation. Reloading the file list also asks before discarding unsaved changes.

Until a custom selection is saved, the default includes `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, YAML under `packages/`, `themes/`, `blueprints/`, and supported web assets under `www/`.

## Push to GitHub

1. Choose a destination branch. For a first trial, select **Create new branch** and enter `ha/updates`. New branches start from `default_branch`.
2. Enter a commit message and select **Review and push**. Save unsaved selection changes if prompted.
3. Inspect every filename and diff, including deletions, then select **Confirm push**.

HA's active configuration is validated before committing. Unselected GitHub files remain untouched. Unchanged content creates no commit, although a requested new branch can be created. YAML line endings are normalized in the Git copy while preserving meaningful block-scalar trailing newlines.

If the GitHub branch moves after previewing, push is rejected; review again. There is no automatic merge. A preview expires after 15 minutes; local file or dashboard changes invalidate it.

## Import from GitHub

1. Choose the source branch and select **Review and import**.
2. Inspect filenames and diffs. Missing local files are preserved by default. Enable **Also delete local files missing from the branch** before previewing only if you want them removed.
3. Select **Back up and import**.

Import validates the current configuration, waits for a completed Supervisor backup, saves a local recovery snapshot and persistent journal, updates files and validates HA again. The optional dashboard is updated through its API. If applying or validation fails, originals are restored. Each file is replaced atomically; the complete update is not one atomic operation. Avoid concurrent editing during import.

The backup includes **Home Assistant, secrets, internal settings and its database**. Other add-ons and the host OS are excluded. Supervisor manages these backups; the add-on does not delete them. Local recovery snapshots are stored separately in `/data/snapshots`.

File changes do not restart HA automatically. Select **Validate and restart HA** when ready. Dashboard API changes take effect immediately. Use configuration appropriate for your installed HA version; validation does not simulate an upgrade.

## Optional dashboard sync

Select **Load dashboards**, choose an existing dashboard, enter a file such as `dashboards/overview.yaml`, enable sync and select **Save dashboard selection**. The dashboard must be editable in the HA UI (storage mode). The add-on does not create dashboards or write directly to `.storage`.

Push exports the chosen dashboard; import requires its Git file in the selected branch and uses `lovelace/config/save`. One dashboard can be mapped at a time. YAML dashboards on disk can instead be selected as ordinary files. API sync takes precedence over a disk file with the same path while enabled. When disabled, explicitly selected disk files are handled normally.

Dashboard resources and HACS cards are not synced; install required cards separately on the receiving installation.

## Recovery and troubleshooting

- **Connection fails:** check `owner/repo`, an initialized base branch, deploy-key write access and outbound SSH access.
- **Source missing from the store:** confirm source visibility, refresh the store or use local installation.
- **Invalid YAML or suspected secrets:** inspect reported files locally, move credentials into `secrets.yaml` and reference them with `!secret`.
- **Backup fails:** active files remain unchanged.
- **Interrupted import:** the journal blocks new sync operations after restart until recovery. Select **Restore last update**.
- **Manual restore:** later changes to affected files and the mapped dashboard are overwritten; the panel asks first.
- **Core or ingress unavailable:** use HA's normal backup recovery tools. Dashboard API and validation may be unavailable even when file recovery works. Do not uninstall or delete add-on data during recovery.

Restore does not restart Core automatically. If Git ignore rules prevent staging the reviewed files, push stops; fix those rules and review again. There is no scheduling, automatic merge or full host backup.

## Updates

For store installations, use **Update** when offered. Keep add-on data and its deploy key.

For local installations, stop the add-on and update its code:

```sh
git -C /share/ha-git-sync-source pull --ff-only origin main
cp -R /share/ha-git-sync-source/ha_git_sync/. /addons/ha_git_sync/
ha store reload
```

Select **Update** if offered, otherwise **Rebuild**, then start. Do not uninstall to update. Reload the panel if old UI text remains.

## Scope and security

Custom selections accept supported YAML/YML, JSON, text, Markdown, CSV, Python, shell scripts, Jinja, XML, INI/CONF, JavaScript/CSS, SVG, images and web fonts. Limits: 10 MB per file, 64 MB total.

Protected paths cannot be selected: hidden paths (including `.storage`), names containing `secret`, databases, logs, certificates/private-key file types, `custom_components`, `www/community`, `zigbee2mqtt`, `known_devices.yaml` and `ip_bans.yaml`. Symbolic links are rejected. Unselected GitHub files are preserved.

Secret scanning is a heuristic, not a guarantee. Review contents and use a private repository. Deselecting a secret does not remove previously uploaded secrets from Git history. Import only trusted configuration because it may contain executable commands.

Only HA ingress exposes the panel; there is no external port. The internal ingress peer address is a Supervisor convention, not a user's HA instance address. Mutating requests require a CSRF token and only one operation runs at a time. Supervisor admin access supports backup, checks and restart. The Supervisor token is excluded from Git/SSH subprocesses.

## Development

Run backend tests on Linux, the add-on runtime:

```sh
python -m pip install -r requirements-dev.txt -r ha_git_sync/requirements.txt
python -m unittest discover -s ha_git_sync/tests -v
node --test ha_git_sync/tests/test_frontend.cjs
docker build -t ha-git-sync:local ha_git_sync
```

Tests use temporary local Git repositories and a simulated Supervisor/dashboard. Verify real ingress, language detection, backup and API permissions on a test HA installation before production use.
