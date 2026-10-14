"""Exercise real Git repositories and transaction failures without touching HA."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from engine import Engine
from files import SyncError, canonical_yaml, inventory, managed, parse_dashboard, scan_secrets, text_diff, validate_yaml
from server import create_app


class FakeHA:
    def __init__(self):
        self.checks = 0
        self.backups = 0
        self.fail_check = None
        self.fail_backup = False
        self.after_backup = None
        self.fail_save_once = False
        self.dashboard_path = "lovelace"
        self.config = {"views": [{"title": "Original"}]}
        self.restarts = 0

    def check(self):
        self.checks += 1
        if self.checks == self.fail_check:
            raise SyncError("Invalid config")

    def backup(self):
        self.backups += 1
        if self.fail_backup:
            raise SyncError("Backup failed")
        if self.after_backup:
            self.after_backup()
        return "backup-test"

    def dashboard(self):
        return copy.deepcopy(self.config)

    def save_dashboard(self, config):
        if self.fail_save_once:
            self.fail_save_once = False
            raise SyncError("Dashboard save failed")
        self.config = copy.deepcopy(config)

    def dashboards(self):
        return [{"title": "Overview", "url_path": "lovelace", "mode": "storage"}]

    def restart(self):
        self.restarts += 1


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote"
        self.remote.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "receive.denyCurrentBranch", "ignore")
        self.config = self.root / "config"
        self.config.mkdir()
        initial = {"configuration.yaml": b"default_config:\n# baseline\n", "automations.yaml": b"[]\n",
                   "scripts.yaml": b"", "scenes.yaml": b"", "www/image.svg": b"<svg/>\n",
                   "README.md": b"Keep this\n", "docs/notes.md": b"Documentation\n",
                   "dashboards/overview.yaml": b"views:\n  - title: Original\n"}
        for name, content in initial.items():
            path = self.remote / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if managed(name):
                local = self.config / name
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(content)
        (self.config / "secrets.yaml").write_text("password: do-not-copy\n")
        (self.config / ".storage").mkdir()
        (self.config / ".storage/lovelace").write_text("do-not-touch")
        (self.config / "www/community").mkdir()
        (self.config / "www/community/card.js").write_text("keep installed card")
        self.commit()
        self.ha = FakeHA()
        self.options = {"repository": str(self.remote), "default_branch": "main", "dashboard_sync": False, "dashboard_file": "dashboards/overview.yaml"}
        self.engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.remote, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-m", "Change")

    def change_remote(self, name="configuration.yaml", content="default_config:\n# updated\n"):
        path = self.remote / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.commit()

    def test_push_new_branch_preserves_docs_and_excludes_secrets(self):
        (self.config / "configuration.yaml").write_text("default_config:\n# local\n")
        plan = self.engine.preview("push", "ha/updates")
        self.assertTrue(plan["new_branch"])
        result = self.engine.push(plan["id"], "Save HA")
        self.assertTrue(result["changed"])
        self.assertEqual(self.git("show", "ha/updates:README.md"), "Keep this")
        self.assertEqual(self.git("show", "ha/updates:docs/notes.md"), "Documentation")
        names = self.git("ls-tree", "-r", "--name-only", "ha/updates").splitlines()
        self.assertNotIn("secrets.yaml", names)
        self.assertNotIn(".storage/lovelace", names)
        self.assertNotIn("www/community/card.js", names)
        self.assertNotEqual(self.git("rev-parse", "main"), result["commit"])

    def test_push_rejects_concurrent_remote_change(self):
        (self.config / "configuration.yaml").write_text("default_config:\n# local\n")
        plan = self.engine.preview("push", "main")
        self.change_remote("docs/notes.md", "Concurrent change\n")
        expected = self.git("rev-parse", "main")
        with self.assertRaises(SyncError):
            self.engine.push(plan["id"], "Save")
        self.assertEqual(self.git("rev-parse", "main"), expected)

    def test_stale_local_preview_is_rejected(self):
        self.change_remote()
        plan = self.engine.preview("pull", "main")
        (self.config / "configuration.yaml").write_text("default_config:\n# edit after preview\n")
        with self.assertRaisesRegex(SyncError, "ändrades efter"):
            self.engine.pull(plan["id"])
        self.assertEqual(self.ha.backups, 0)

    def test_pull_uses_previewed_commit_even_if_branch_moves(self):
        self.change_remote()
        plan = self.engine.preview("pull", "main")
        self.change_remote(content="default_config:\n# later\n")
        result = self.engine.pull(plan["id"])
        self.assertEqual(result["commit"], plan["commit"])
        self.assertIn("updated", (self.config / "configuration.yaml").read_text())
        self.assertEqual(self.ha.backups, 1)
        self.assertEqual(self.ha.restarts, 0)

    def test_backup_failure_never_changes_live_files(self):
        self.change_remote()
        before = inventory(self.config)
        self.ha.fail_backup = True
        plan = self.engine.preview("pull", "main")
        with self.assertRaises(SyncError):
            self.engine.pull(plan["id"])
        self.assertEqual(inventory(self.config), before)

    def test_edit_during_backup_stops_apply(self):
        self.change_remote()
        self.ha.after_backup = lambda: (self.config / "configuration.yaml").write_text("default_config:\n# edit during backup\n")
        plan = self.engine.preview("pull", "main")
        with self.assertRaisesRegex(SyncError, "under backupen"):
            self.engine.pull(plan["id"])
        self.assertIn("edit during backup", (self.config / "configuration.yaml").read_text())

    def test_failed_config_check_restores_modified_added_and_deleted_files(self):
        (self.remote / "www/image.svg").unlink()
        self.change_remote("packages/new.yaml", "sensor: []\n")
        before = inventory(self.config)
        self.ha.fail_check = 2
        plan = self.engine.preview("pull", "main", allow_deletions=True)
        with self.assertRaisesRegex(SyncError, "återställts"):
            self.engine.pull(plan["id"])
        self.assertEqual(inventory(self.config), before)
        self.assertEqual(self.engine.read_journal()["phase"], "restored")
        self.assertEqual((self.config / ".storage/lovelace").read_text(), "do-not-touch")
        self.assertTrue((self.config / "www/community/card.js").exists())

    def test_manual_restore_survives_engine_restart(self):
        self.change_remote()
        before = inventory(self.config)
        plan = self.engine.preview("pull", "main")
        self.engine.pull(plan["id"])
        engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)
        engine.restore()
        self.assertEqual(inventory(self.config), before)

    def test_interrupted_transaction_blocks_sync_until_restore(self):
        self.change_remote()
        plan_result = self.engine.preview("pull", "main")
        plan = self.engine.plans[plan_result["id"]]
        journal = self.engine.snapshot(plan, "backup-test")
        journal["phase"] = "applying"
        self.engine.write_journal(journal)
        (self.config / "configuration.yaml").write_text("partial update\n")
        engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)
        with self.assertRaisesRegex(SyncError, "avbrutna"):
            engine.preview("pull", "main")
        engine.restore()
        self.assertIn("baseline", (self.config / "configuration.yaml").read_text())

    def test_dashboard_export_and_import_use_api(self):
        self.engine.dashboard_sync = True
        self.ha.config = {"views": [{"title": "From HA"}]}
        plan = self.engine.preview("push", "ha/dashboard")
        self.engine.push(plan["id"], "Export dashboard")
        self.assertEqual(parse_dashboard(self.git("show", "ha/dashboard:dashboards/overview.yaml").encode()), self.ha.config)
        plan = self.engine.preview("pull", "main")
        self.engine.pull(plan["id"])
        self.assertEqual(self.ha.config["views"][0]["title"], "Original")
        self.engine.restore()
        self.assertEqual(self.ha.config["views"][0]["title"], "From HA")

    def test_dashboard_api_failure_rolls_back_files_and_dashboard(self):
        self.engine.dashboard_sync = True
        self.change_remote("dashboards/overview.yaml", "views:\n  - title: New\n")
        before = inventory(self.config)
        self.ha.fail_save_once = True
        plan = self.engine.preview("pull", "main")
        with self.assertRaisesRegex(SyncError, "återställts"):
            self.engine.pull(plan["id"])
        self.assertEqual(inventory(self.config), before)
        self.assertEqual(self.ha.config["views"][0]["title"], "Original")

    def test_custom_dashboard_file_is_used_for_export_and_import(self):
        self.engine.configure_dashboard(True, "lovelace", "dashboards/rooms/overview.yml")
        self.ha.config = {"views": [{"title": "Generic dashboard"}]}
        plan = self.engine.preview("push", "ha/generic-dashboard")
        self.assertIn("dashboards/rooms/overview.yml", [c["path"] for c in plan["changes"]])
        self.engine.push(plan["id"], "Export dashboard")
        self.assertEqual(parse_dashboard(self.git("show", "ha/generic-dashboard:dashboards/rooms/overview.yml").encode()), self.ha.config)
        self.ha.config = {"views": [{"title": "Local edit"}]}
        plan = self.engine.preview("pull", "ha/generic-dashboard")
        self.engine.pull(plan["id"])
        self.assertEqual(self.ha.config["views"][0]["title"], "Generic dashboard")
        self.engine.restore()
        self.assertEqual(self.ha.config["views"][0]["title"], "Local edit")

    def test_dashboard_settings_are_persistent_and_invalidate_previews(self):
        plan = self.engine.preview("push", "ha/old-preview")
        self.engine.configure_dashboard(True, "lovelace", "dashboards/my-own.yaml")
        self.assertEqual(self.engine.plans, {})
        with self.assertRaises(SyncError):
            self.engine.push(plan["id"], "Old preview")
        engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)
        self.assertTrue(engine.dashboard_sync)
        self.assertEqual(engine.status()["dashboard_file"], "dashboards/my-own.yaml")

    def test_dashboard_settings_reject_unsafe_paths_and_unknown_target(self):
        for name in ["configuration.yaml", "../dashboard.yaml", "/dashboards/view.yaml", "dashboards/../secrets.yaml", "dashboards/.private/a.yaml", "dashboards/secrets.yaml", "dashboards/config.json"]:
            with self.assertRaises(SyncError):
                self.engine.configure_dashboard(True, "lovelace", name)
        with self.assertRaises(SyncError):
            self.engine.configure_dashboard(True, "not-a-dashboard", "dashboards/view.yaml")
        self.assertFalse(self.engine.dashboard_settings.exists())

    def test_generic_default_stays_stable_after_repository_is_initialized(self):
        options = {**self.options, "dashboard_file": ""}
        engine = Engine(self.config, self.root / "fresh-data", options, self.ha, allow_local=True)
        self.assertEqual(engine.dashboard_file, "dashboards/dashboard.yaml")
        engine.branches()
        engine = Engine(self.config, self.root / "fresh-data", options, self.ha, allow_local=True)
        self.assertEqual(engine.dashboard_file, "dashboards/dashboard.yaml")

    def test_repository_cache_does_not_choose_a_dashboard_filename(self):
        self.engine.branches()
        (self.root / "data/dashboard_default.txt").unlink()
        options = {**self.options, "dashboard_file": ""}
        engine = Engine(self.config, self.root / "data", options, self.ha, allow_local=True)
        self.assertEqual(engine.dashboard_file, "dashboards/dashboard.yaml")

    def test_explicit_saved_dashboard_default_survives_upgrade(self):
        (self.root / "data/dashboard_default.txt").write_text("dashboards/custom.yaml")
        options = {**self.options, "dashboard_file": ""}
        engine = Engine(self.config, self.root / "data", options, self.ha, allow_local=True)
        self.assertEqual(engine.dashboard_file, "dashboards/custom.yaml")

    def test_missing_custom_dashboard_file_stops_pull(self):
        self.engine.configure_dashboard(True, "lovelace", "dashboards/not-in-main.yaml")
        with self.assertRaisesRegex(SyncError, "not-in-main.yaml"):
            self.engine.preview("pull", "main")
        self.assertEqual(self.ha.backups, 0)

    def test_restore_uses_original_target_after_dashboard_selection_changes(self):
        self.engine.dashboard_sync = True
        self.change_remote("dashboards/overview.yaml", "views:\n  - title: Incoming\n")
        plan = self.engine.preview("pull", "main")
        self.engine.pull(plan["id"])
        self.ha.dashboards = lambda: [{"title": "Other", "url_path": "dashboard-other", "mode": "storage"}]
        self.engine.configure_dashboard(True, "dashboard-other", "dashboards/other.yaml")
        targets = []
        original_save = self.ha.save_dashboard
        def save(config):
            targets.append(self.ha.dashboard_path)
            original_save(config)
        self.ha.save_dashboard = save
        self.engine.restore()
        self.assertEqual(targets, ["lovelace"])
        self.assertEqual(self.ha.dashboard_path, "dashboard-other")

    def test_no_changes_does_not_backup_or_commit(self):
        plan = self.engine.preview("pull", "main")
        self.assertEqual(self.engine.pull(plan["id"]), {"changed": False})
        self.assertEqual(self.ha.backups, 0)
        plan = self.engine.preview("push", "main")
        self.assertEqual(self.engine.push(plan["id"], "Save"), {"changed": False})

    def test_new_branch_can_be_created_without_config_changes(self):
        before = self.git("rev-parse", "main")
        plan = self.engine.preview("push", "ha/new-empty")
        self.assertEqual(plan["changes"], [])
        result = self.engine.push(plan["id"], "Create branch")
        self.assertTrue(result["branch_created"])
        self.assertFalse(result["changed"])
        self.assertEqual(self.git("rev-parse", "ha/new-empty"), before)

    def test_unexpected_staged_file_blocks_push(self):
        (self.config / "configuration.yaml").write_text("default_config:\n# new\n")
        plan = self.engine.preview("push", "ha/guard")
        original_git = self.engine.git
        def stage_extra(*args, **kwargs):
            result = original_git(*args, **kwargs)
            if args[0] == "add":
                (kwargs["cwd"] / "README.md").write_text("unexpected change\n")
                original_git("add", "README.md", **kwargs)
            return result
        with patch.object(self.engine, "git", side_effect=stage_extra):
            with self.assertRaisesRegex(SyncError, "index stämmer inte"):
                self.engine.push(plan["id"], "Save")
        self.assertNotIn("ha/guard", self.git("branch", "--list"))

    def test_pull_preserves_local_only_files_unless_deletion_is_selected(self):
        (self.config / "packages").mkdir()
        (self.config / "packages/local.yaml").write_text("sensor: []\n")
        plan = self.engine.preview("pull", "main")
        self.assertEqual(plan["changes"], [])
        self.assertEqual(plan["kept_local"], ["packages/local.yaml"])
        plan = self.engine.preview("pull", "main", allow_deletions=True)
        self.assertEqual(plan["changes"][0]["action"], "tas bort")
        self.engine.pull(plan["id"])
        self.assertFalse((self.config / "packages/local.yaml").exists())
        self.engine.restore()
        self.assertTrue((self.config / "packages/local.yaml").exists())

    def test_preview_diff_is_readable_and_hides_removed_credentials(self):
        self.change_remote()
        plan = self.engine.preview("pull", "main")
        self.assertIn("+# updated", plan["changes"][0]["diff"])
        preview = text_diff("configuration.yaml", b"password: do-not-show\n", b"password: !secret password\n")
        self.assertNotIn("do-not-show", preview)
        self.assertIn("döljs", preview)

    def test_retention_keeps_latest_snapshot_and_restore_works(self):
        self.engine.options["snapshot_retention"] = 2
        for index in range(4):
            self.change_remote(content=f"default_config:\n# iteration {index}\n")
            plan = self.engine.preview("pull", "main")
            self.engine.pull(plan["id"])
        folders = list((self.root / "data/snapshots").iterdir())
        self.assertEqual(len(folders), 2)
        self.assertTrue(Path(self.engine.read_journal()["snapshot"]).exists())
        self.engine.restore()
        self.assertIn("iteration 2", (self.config / "configuration.yaml").read_text())

    def test_invalid_yaml_and_duplicate_keys_rejected_before_backup(self):
        self.change_remote(content="default_config: [\n")
        with self.assertRaisesRegex(SyncError, "Ogiltig YAML"):
            self.engine.preview("pull", "main")
        self.assertEqual(self.ha.backups, 0)
        with self.assertRaises(SyncError):
            validate_yaml({"configuration.yaml": b"key: one\nkey: two\n"})

    def test_secret_scan_never_reports_values(self):
        (self.config / "configuration.yaml").write_text("password: super-private-value\n")
        with self.assertRaises(SyncError) as result:
            self.engine.preview("push", "main")
        self.assertIn("configuration.yaml", str(result.exception))
        self.assertNotIn("super-private-value", str(result.exception))
        self.assertEqual(scan_secrets({"configuration.yaml": b"password: !secret password\n"}), [])

    def test_symlinked_file_and_directory_rejected(self):
        (self.config / "packages").mkdir()
        (self.config / "packages/leak.yaml").symlink_to(self.config / "secrets.yaml")
        with self.assertRaisesRegex(SyncError, "Symbolisk"):
            inventory(self.config)
        (self.config / "packages/leak.yaml").unlink()
        (self.config / "packages").rmdir()
        (self.config / "packages").symlink_to(self.root / "missing")
        with self.assertRaisesRegex(SyncError, "Symbolisk"):
            inventory(self.config)

    def test_allowlist_excludes_nested_secrets_and_runtime(self):
        for name in ["secrets.yaml", "packages/secrets.yaml", "packages/.private/foo.yaml", "../configuration.yaml", "www/community/card.js", "zigbee2mqtt/configuration.yaml", "custom_components/test.py", "www/private.key", "home-assistant_v2.db"]:
            self.assertFalse(managed(name), name)

    def test_nonexistent_pull_branch_and_invalid_branch_rejected(self):
        for branch in ["missing", "../main", "--upload-pack=bad", "main;bad"]:
            with self.assertRaises(SyncError):
                self.engine.preview("pull", branch)

    def test_expired_preview_is_rejected(self):
        plan = self.engine.preview("pull", "main")
        self.engine.plans[plan["id"]]["created"] -= 901
        with self.assertRaisesRegex(SyncError, "gått ut"):
            self.engine.pull(plan["id"])

    def test_operation_lock_prevents_overlap(self):
        with self.engine.operation():
            with self.assertRaisesRegex(SyncError, "annan operation"):
                self.engine.branches()

    def test_yaml_line_endings_do_not_create_false_changes(self):
        (self.config / "configuration.yaml").write_bytes(b"default_config:\r\n# baseline\r\n\r\n")
        plan = self.engine.preview("push", "main")
        self.assertEqual(plan["changes"], [])
        plan = self.engine.preview("pull", "main")
        self.assertEqual(plan["changes"], [])

    def test_block_scalar_trailing_newlines_are_preserved(self):
        content = b"message: |+\n  keep trailing newlines\n\n\n"
        self.assertEqual(canonical_yaml({"packages/test.yaml": content})["packages/test.yaml"], content)

    def test_yaml_merge_overrides_are_valid(self):
        validate_yaml({"configuration.yaml": b"defaults: &default\n  enabled: true\nitem:\n  <<: *default\n  enabled: false\n"})

    def test_token_inside_command_is_flagged_without_value(self):
        content = b"shell_command:\n  upload: 'curl -H \"Authorization: Bearer abcdefghijklmnopqrstuvwxyz\" example'\n"
        self.assertEqual(scan_secrets({"configuration.yaml": content}), ["configuration.yaml"])

    def test_last_successful_operation_is_persistent(self):
        (self.config / "configuration.yaml").write_text("default_config:\n# persist\n")
        plan = self.engine.preview("push", "ha/persistent")
        result = self.engine.push(plan["id"], "Save")
        engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)
        self.assertEqual(engine.status()["last_result"]["commit"], result["commit"])

    def test_custom_root_yaml_can_be_selected_and_pushed(self):
        (self.config / "custom.yaml").write_text("sensor: []\n")
        self.assertNotIn("custom.yaml", self.engine.current())
        catalogue = self.engine.scope_catalog()
        entry = next(e for e in catalogue["entries"] if e["path"] == "custom.yaml")
        self.assertFalse(entry["blocked"])
        self.engine.configure_scope(["custom.yaml"], [])
        plan = self.engine.preview("push", "ha/custom-file")
        self.assertEqual([c["path"] for c in plan["changes"]], ["custom.yaml"])
        self.engine.push(plan["id"], "Save custom file")
        self.assertEqual(self.git("show", "ha/custom-file:custom.yaml"), "sensor: []")
        self.assertEqual(self.git("show", "ha/custom-file:configuration.yaml"), "default_config:\n# baseline")

    def test_folder_selection_includes_future_files_and_respects_exclusions(self):
        folder = self.config / "my-config"
        folder.mkdir()
        (folder / "one.yaml").write_text("sensor: []\n")
        (folder / "skip.yaml").write_text("sensor: []\n")
        (folder / "secrets.yaml").write_text("password: private\n")
        self.engine.configure_scope(["my-config/"], ["my-config/skip.yaml"])
        (folder / "later.yaml").write_text("sensor: []\n")
        self.assertEqual(set(self.engine.current()), {"my-config/one.yaml", "my-config/later.yaml"})

    def test_scope_persists_and_invalidates_preview(self):
        plan = self.engine.preview("push", "ha/old-scope")
        self.engine.configure_scope(["custom.yaml"], [])
        self.assertEqual(self.engine.plans, {})
        with self.assertRaises(SyncError):
            self.engine.push(plan["id"], "Old")
        engine = Engine(self.config, self.root / "data", self.options, self.ha, allow_local=True)
        self.assertEqual(engine.scope.includes, ["custom.yaml"])

    def test_selected_remote_only_file_can_be_imported_and_restored_after_scope_change(self):
        self.change_remote("custom.yaml", "sensor: []\n")
        before = (self.config / "configuration.yaml").read_bytes()
        self.engine.configure_scope(["custom.yaml"], [])
        plan = self.engine.preview("pull", "main")
        self.engine.pull(plan["id"])
        self.assertEqual((self.config / "custom.yaml").read_text(), "sensor: []\n")
        self.assertEqual((self.config / "configuration.yaml").read_bytes(), before)
        self.engine.configure_scope(["themes/"], [])
        self.engine.restore()
        self.assertFalse((self.config / "custom.yaml").exists())

    def test_protected_paths_cannot_be_selected_even_with_folder_includes(self):
        for name in ["secrets.yaml", ".storage/", "../config/", "zigbee2mqtt/", "www/community/", "custom_components/", "database.db", "/config/custom.yaml", "known_devices.yaml"]:
            with self.assertRaises(SyncError):
                self.engine.configure_scope([name], [])
        entries = {e["path"]: e for e in self.engine.scope_catalog()["entries"]}
        self.assertTrue(entries["secrets.yaml"]["blocked"])
        self.assertTrue(entries[".storage/"]["blocked"])
        self.assertNotIn(".storage/lovelace", entries)

    def test_deselected_files_are_not_deleted_from_github(self):
        self.change_remote("custom.yaml", "sensor: []\n")
        (self.config / "configuration.yaml").write_text("default_config:\n# changed\n")
        self.engine.configure_scope(["configuration.yaml"], [])
        plan = self.engine.preview("push", "ha/selected")
        self.engine.push(plan["id"], "Only config")
        self.assertEqual(self.git("show", "ha/selected:custom.yaml"), "sensor: []")

    def test_selected_symlink_is_rejected(self):
        (self.config / "custom.yaml").symlink_to(self.config / "secrets.yaml")
        with self.assertRaisesRegex(SyncError, "Symbolisk"):
            self.engine.configure_scope(["custom.yaml"], [])

    def test_selected_json_with_credentials_is_blocked(self):
        (self.config / "extra.json").write_text('{"mqtt_password": "private-value"}')
        self.engine.configure_scope(["extra.json"], [])
        with self.assertRaises(SyncError) as error:
            self.engine.preview("push", "ha/json")
        self.assertNotIn("private-value", str(error.exception))

    def test_plaintext_config_and_script_credentials_are_blocked(self):
        for name, data in [("config.ini", b"mqtt_password=private-value\n"), ("helper.py", b"API_KEY = 'private-value'\n")]:
            self.assertEqual(scan_secrets({name: data}), [name])

    def test_regular_dashboard_files_and_api_mapping_do_not_collide(self):
        folder = self.config / "dashboards"
        folder.mkdir()
        (folder / "overview.yaml").write_text("views:\n  - title: Disk\n")
        self.engine.configure_scope(["dashboards/"], [])
        self.engine.configure_dashboard(True, "lovelace", "dashboards/overview.yaml")
        self.assertEqual(parse_dashboard(self.engine.current()["dashboards/overview.yaml"]), self.ha.config)

    def test_disk_dashboard_import_and_restore_when_api_sync_disabled(self):
        path = self.config / "dashboards/overview.yaml"
        path.parent.mkdir(exist_ok=True)
        original = b"views:\n  - title: Local\n"
        path.write_bytes(original)
        self.engine.configure_scope(["dashboards/"], [])
        plan = self.engine.preview("pull", "main")
        self.engine.pull(plan["id"])
        self.assertEqual(parse_dashboard(path.read_bytes())["views"][0]["title"], "Original")
        self.assertEqual(self.ha.config["views"][0]["title"], "Original")
        self.assertIn("dashboards/overview.yaml", [p["name"] for p in self.engine.read_journal()["paths"]])
        self.engine.restore()
        self.assertEqual(path.read_bytes(), original)

    def test_disk_dashboard_deletion_and_restore_when_api_sync_disabled(self):
        path = self.config / "dashboards/overview.yaml"
        path.parent.mkdir(exist_ok=True)
        original = b"views: []\n"
        path.write_bytes(original)
        self.engine.configure_scope(["dashboards/"], [])
        (self.remote / "dashboards/overview.yaml").unlink()
        self.commit()
        plan = self.engine.preview("pull", "main", allow_deletions=True)
        self.engine.pull(plan["id"])
        self.assertFalse(path.exists())
        self.engine.restore()
        self.assertEqual(path.read_bytes(), original)

    def test_http_requires_ingress_and_csrf(self):
        app = create_app(self.engine, testing=False)
        client = app.test_client()
        self.assertEqual(client.get("/api/status").status_code, 403)
        trusted = {"REMOTE_ADDR": "172.30.32.2"}
        response = client.get("/api/status", environ_overrides=trusted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post("/api/jobs", json={"action": "branches"}, environ_overrides=trusted).status_code, 403)
        csrf = response.json["csrf"]
        self.assertEqual(client.post("/api/jobs", json={"action": "unknown"}, headers={"X-CSRF-Token": csrf}, environ_overrides=trusted).status_code, 400)
        response = client.post("/api/jobs", json={"action": "branches"}, headers={"X-CSRF-Token": csrf}, environ_overrides=trusted)
        self.assertEqual(response.status_code, 202)
        for _ in range(100):
            job = client.get("/api/jobs/" + response.json["id"], environ_overrides=trusted).json
            if job["done"]:
                break
            time.sleep(.02)
        self.assertTrue(job["done"])
        self.assertEqual(job["result"], ["main"])

    def test_panel_can_reattach_to_running_job_after_reload(self):
        app = create_app(self.engine, testing=True)
        client = app.test_client()
        csrf = client.get("/api/status").json["csrf"]
        ready = threading.Event()
        release = threading.Event()
        def wait_for_release():
            ready.set()
            release.wait(timeout=5)
        self.ha.check = wait_for_release
        response = client.post("/api/jobs", json={"action": "restart"}, headers={"X-CSRF-Token": csrf})
        try:
            self.assertTrue(ready.wait(timeout=2))
            active = client.get("/api/status").json["active_job"]
            self.assertEqual(active["id"], response.json["id"])
            self.assertEqual(active["action"], "restart")
            self.assertEqual(client.post("/api/jobs", json={"action": "branches"}, headers={"X-CSRF-Token": csrf}).status_code, 409)
        finally:
            release.set()
        for _ in range(100):
            if client.get("/api/jobs/" + response.json["id"]).json["done"]:
                break
            time.sleep(.01)
        self.assertIsNone(client.get("/api/status").json["active_job"])


if __name__ == "__main__":
    unittest.main()
