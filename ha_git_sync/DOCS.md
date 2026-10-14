# HA Git Sync

Back up selected Home Assistant configuration files and a UI-managed dashboard to your own GitHub repository. Review changes before uploading or restoring them.

**Install and update through the Home Assistant app/add-on store.** No terminal, Git commands, manually generated SSH keys or GitHub access token are needed. HACS installs integrations and frontend extensions; this project is a Supervisor add-on and uses the app/add-on store instead.

The interface is Swedish when your Home Assistant profile uses Swedish, otherwise English. You can also choose the language in the panel. This guide uses the English button names.

## Before you begin

You need:

- Home Assistant OS on supported amd64/aarch64 hardware, an administrator login and the app/add-on store. HA OS installed directly on a computer is supported. Standalone Core and Container do not provide the required Supervisor services.
- A free [GitHub account](https://github.com/signup). If you do not have one, create an account, verify your email and sign in.
- Internet access. The add-on connects to GitHub using SSH on port 22.

## 1. Install from Home Assistant's app/add-on store

1. Open **Settings → Apps → Install app**. Older versions call this **Settings → Add-ons → Add-on store**.
2. In the store, open the upper-right **⋮** menu and choose **Repositories**.
3. On this project's GitHub page, open **Code**, choose **HTTPS** and copy the repository URL. Paste that URL into Home Assistant and select **Add**.
4. Close the dialog and refresh the store page if necessary.
5. Find **HA Git Sync**, open it and select **Install**. Wait until installation finishes; the first build can take several minutes.
6. Open the add-on's **Configuration** tab before selecting Start.

The app source repository must be publicly accessible for this store installation to work. If HA cannot add the repository, see Troubleshooting below.

## 2. Configure the add-on before starting it

In **Configuration**, change **GitHub repository** (`repository`) to the name of your existing, initialized private backup repository, for example `YOUR-USERNAME/ha-config`. Use only `owner/name`: no `https://`, spaces or `.git` suffix.

For your first setup, leave all other options at their defaults. In particular, leave dashboard sync off; you will choose the dashboard in the panel later.

| Setting | What to enter for the first setup |
| --- | --- |
| GitHub repository (`repository`) | Your actual `YOUR-USERNAME/ha-config`. This is the one required change. |
| Base branch (`default_branch`) | `main`, or the branch name shown in your GitHub repository. |
| Suggested push branch (`push_branch`) | Leave `ha/updates`. The panel lets you choose another branch. |
| Commit author name (`git_name`) | Leave `Home Assistant` or enter your preferred name. |
| Commit author email (`git_email`) | Leave the example value for setup, or use a GitHub no-reply address from [GitHub email settings](https://github.com/settings/emails). This is an author label, not a login or password. |
| Dashboard sync (`dashboard_sync`) | Leave off. |
| Dashboard URL path (`dashboard_url_path`) | Leave `lovelace`. Choose the actual dashboard in the panel later. |
| Dashboard Git file (`dashboard_file`) | Leave empty. Choose a filename in the panel later. |
| Recovery snapshots (`snapshot_retention`) | Leave `3`. |

Select **Save**. Then open **Info**, enable **Start on boot** and **Show in sidebar** if desired, select **Start**, and then **Open Web UI**.

If you edit options in this Configuration tab later, save and restart the add-on. Settings saved inside the Git Sync panel take effect immediately. For dashboard changes after initial setup, use the panel: a dashboard selection already saved there takes priority over Configuration-tab defaults.

## 3. Connect the add-on to GitHub using its generated key

An SSH key is the add-on's access credential. The add-on creates it for you. You copy only its **public key** to GitHub; its private key stays in the add-on.

1. In the Git Sync panel, select **Create SSH key**. A box containing a long line beginning with `ssh-ed25519` appears.
2. Select **Copy key**. If automatic copying is unavailable, select and copy the entire line manually.
3. Select **Open deploy keys**. This opens the settings for the repository you entered. Sign in to GitHub if asked.
4. Confirm the repository name at the top is **your backup repository**.
5. On GitHub, select **Add deploy key**.
6. In **Title**, enter `Home Assistant Git Sync`.
7. In **Key**, paste the entire public key line.
8. Enable **Allow write access**. This is required to upload files; without it the key is read-only.
9. Select **Add key**. GitHub may ask you to confirm your password or account authentication.
10. Return to Home Assistant and select **Test connection**. The branch list should load.

If you opened GitHub manually, the route is **your backup repository → Settings → Deploy keys → Add deploy key**. Use the repository's Settings tab, rather than your account's SSH-key settings.

You do not need to generate keys on your computer, install an SSH app or create a personal access token. Keep this deploy key for future updates; a normal add-on update preserves it.

## 4. Choose what to sync

### Ordinary configuration files

1. Select **Show my files and folders** in the panel.
2. Check the files or folders you want to back up.
3. Select **Save file selection**.

Whole-folder selections include future eligible files in that folder. **Extra paths** adds files not yet present locally; **Custom exclusions** skips specific files or folders. Enter one relative path per line; folder names end with `/`.

The same saved selection applies to upload and import. Deselecting a file does not delete it from HA or GitHub. If you change checkboxes, extra paths or exclusions without saving, the next push/import asks you to save first. Cancel returns to editing without syncing.

### Dashboards created and edited in the Home Assistant UI

Use **Optional dashboard** for a dashboard you create and edit with HA's **Edit dashboard**, **Add card**, and **Add view** controls. HA stores this dashboard internally; selecting ordinary configuration files does not export it.

This option exports the dashboard's layout as a YAML file in GitHub, then restores that layout through HA's dashboard API. The YAML file is a backup/export of the UI dashboard, not a switch to a file-managed dashboard. You continue editing the dashboard in the HA UI after export or import.

**Choose or create an editable dashboard first:**

1. In Home Assistant, open **Settings → Dashboards**.
2. Choose a dashboard you already edit yourself, or select **Add dashboard → New dashboard from scratch**, give it a title and create it.
3. Open that dashboard and check that you can edit its cards and views. If an automatically generated dashboard offers **Take control**, taking control turns off its automatic layout updates. For a first trial, create a separate dashboard from scratch instead.

**Then configure its backup in Git Sync:**

1. Return to the Git Sync panel and find **Optional dashboard → Select dashboard and Git file**.
2. Select **Load dashboards**.
3. In **Dashboard in Home Assistant**, choose the dashboard you just identified or created. Use the selector; you do not need to type its URL path.
4. In **YAML file in the Git repository**, enter `dashboards/dashboard.yaml`. This is a new destination filename you choose for your GitHub backup; it need not exist in HA or GitHub yet.
5. Enable **Sync the selected dashboard**.
6. Select **Save dashboard selection**. Check the active-selection text beneath the button.
7. Perform a push as described below. The add-on creates the Git file on the first push. Check GitHub to confirm it exists.

To restore it, use **Review and import** from a branch containing that file. The chosen UI dashboard must already exist in HA; importing updates its layout in place and does not create a new dashboard. Dashboard changes appear immediately without an HA restart.

Only one UI dashboard is mapped at a time. This backs up layout and configuration, not entities, integrations, installed custom cards or their resources. Required integrations and cards must also exist on the receiving installation.

**File-managed YAML dashboards:** If your dashboard is defined in a YAML file you maintain yourself, leave optional UI-dashboard sync off and select that existing file in the ordinary file picker. Do not select or copy `.storage` manually. While UI sync is enabled, its export takes priority over a disk file with the same chosen path.

## 5. Make your first upload

A **push** uploads the selected HA files to GitHub. A **commit** is one saved version of those files.

1. Under **Push to GitHub**, choose the destination branch. For a simple backup, choose `main` so the files appear on your repository's default page. The panel initially suggests a separate `ha/updates` branch; if you use it, switch GitHub's branch selector to `ha/updates` to see those files.
2. Leave the commit message at its default, or enter a short description such as `First Home Assistant backup`.
3. Select **Review and push**. If asked about unsaved file selections, confirm to save them first.
4. Inspect the filenames and differences. **Deleted** means that a managed file will be removed from this GitHub branch, not from HA.
5. Select **Confirm push** and wait until it completes.
6. Open your backup repository on GitHub. Select the same branch you pushed to and confirm your files, and the optional dashboard export, are listed.

Existing GitHub files outside your selected scope are preserved. No new commit is needed for unchanged files. An upload does not automatically create or merge a GitHub pull request.

## Restore files or a dashboard from GitHub

Import changes your live HA configuration. Start with a trusted repository and review the changes.

1. Under **Import from GitHub**, select the branch containing the version you want.
2. Leave **Also delete local files missing from the branch** off unless you deliberately want those local files deleted.
3. Select **Review and import** and inspect every change.
4. Select **Back up and import**. The add-on waits for a Home Assistant backup, saves a local recovery point, updates the selected content and validates the configuration.
5. After ordinary file changes, select **Validate and restart HA** when ready. UI-dashboard changes take effect immediately.

A preview expires after 15 minutes. If files, the dashboard or the GitHub branch change after previewing, review again. Avoid editing the affected content during import. Failed applying/validation triggers recovery; **Restore last update** restores the affected originals and overwrites later edits to them.

The HA backup includes HA's database and internal settings, but excludes other apps/add-ons and the host OS. It is separate from the selected files uploaded to GitHub.

## Update through Home Assistant

Updates use the **same app/add-on store you installed from**. The store checks the version published by this source repository; you do not need to download files, copy directories, run Git commands or add it to HACS.

1. When Home Assistant offers a **HA Git Sync** update, open the add-on and read its **Changelog**.
2. Create a backup when prompted, or create one in **Settings → System → Backups** first.
3. Select **Update** and wait for the build/installation to finish. Start the add-on again if it is stopped.
4. Reopen or reload the Git Sync panel.
5. Confirm the repository, saved selections and dashboard mapping are still correct. Your generated SSH key stays in the add-on's persistent data; you normally do not add a new deploy key.

If an announced update is missing, refresh/check for updates in the app/add-on store and confirm this source repository is still listed under **Repositories**. Updates appear after the maintainer publishes a higher version to the store's source branch. Do not uninstall and reinstall to update; uninstalling can remove persistent data.

Updating the add-on changes its program. **Import from GitHub** changes your selected HA files/dashboard. These are different operations.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Source repository cannot be added, or HA Git Sync is missing from the store | Recheck the source URL from the installation section, refresh the store and check HA's Supervisor logs. The source must be publicly accessible. |
| No app/add-on store | This add-on requires HA OS/Supervisor. It cannot be installed through HACS on standalone Core or Container. |
| Add-on stops immediately | Save your actual `owner/repository` in Configuration, then start again. Check the add-on's Log tab. |
| Test connection fails | Add the entire generated key to your backup repository's Deploy keys, enable write access and check internet/SSH access. |
| Base branch is missing | Confirm you enabled Add README when creating the repository; check its actual branch name. |
| GitHub appears unchanged after push | Select the branch you pushed to in GitHub's branch selector. |
| No editable dashboard is listed | Create a dashboard from scratch in HA, or use one whose cards/views you manage manually; then reload the list. YAML-file dashboards use ordinary file selection. |
| Dashboard file missing during import | Push/export it first, or select a branch where the chosen Git file exists. |
| Invalid YAML or suspected secrets | Review the reported file locally; move credentials to `secrets.yaml` and reference them with `!secret`. |
| Backup fails | Active files are not updated. Resolve the HA backup problem before retrying. |
| Interrupted import | Restart the add-on and use Restore last update. If Core/ingress is unavailable, use HA's normal backup recovery tools. Keep add-on data until recovery is complete. |

## What is excluded

Hidden paths, `.storage`, secrets, databases, logs, private-key/certificate file types, `custom_components`, HACS-managed `www/community`, `zigbee2mqtt`, `known_devices.yaml` and `ip_bans.yaml` cannot be selected. Symbolic links are rejected. Limits are 10 MB per file and 64 MB total.

Secret scanning cannot guarantee that every credential is found. Review contents before uploading and use a private backup repository. Removing a secret from a current selection does not erase earlier GitHub history.

## Further help

- [Home Assistant: installing a third-party app repository](https://www.home-assistant.io/common-tasks/os/#installing-a-third-party-app-repository)
- [GitHub: deploy key settings](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
- [Home Assistant: creating and editing dashboards](https://www.home-assistant.io/dashboards/dashboards/)
