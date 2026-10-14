"""Serialized Git operations and journaled file transactions."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from files import (DEFAULT_DASHBOARD_FILE, Scope, SyncError, atomic_write, canonical_yaml, changes, dashboard_bytes, eligible,
                   digest, inventory, parse_dashboard, read_file, safe_path,
                   scan_secrets, text_diff, validate_yaml)
from ha import HomeAssistant

GITHUB_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"


class Engine:
    def __init__(self, config_root=Path("/config"), data_root=Path("/data"), options=None, ha=None, allow_local=False):
        self.config_root = Path(config_root)
        self.data = Path(data_root)
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.data, 0o700)
        self.options = dict(options or {})
        self.scope_settings = self.data / "scope_settings.json"
        try:
            scope_data = json.loads(self.scope_settings.read_text()) if self.scope_settings.exists() else None
            self.scope = Scope(scope_data["includes"], scope_data["excludes"]) if scope_data is not None else Scope(legacy=True)
        except (OSError, ValueError, KeyError, TypeError) as err:
            raise SyncError("Filurvalet kan inte läsas. Kontrollera tilläggets data.") from err
        self.dashboard_settings = self.data / "dashboard_settings.json"
        if self.dashboard_settings.exists():
            try:
                settings = json.loads(self.dashboard_settings.read_text())
                self.options.update({key: settings[key] for key in ("dashboard_sync", "dashboard_url_path", "dashboard_file")})
            except (OSError, ValueError, KeyError, TypeError) as err:
                raise SyncError("Dashboardinställningarna kan inte läsas. Kontrollera tilläggets data.") from err
        default_file = self.data / "dashboard_default.txt"
        if not default_file.exists():
            atomic_write(default_file, DEFAULT_DASHBOARD_FILE.encode())
        self.dashboard_file = self.validate_dashboard_file(self.options.get("dashboard_file") or default_file.read_text())
        repository = self.options.get("repository", "")
        if allow_local:
            self.repository = repository
        elif re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) and not any(p in {".", ".."} for p in repository.split("/")):
            self.repository = f"git@github.com:{repository}.git"
        else:
            raise SyncError("Ange GitHub-repot som ägare/repo.")
        self.allow_local = allow_local
        self.dashboard_sync = bool(self.options.get("dashboard_sync", False))
        self.ha = ha or HomeAssistant(self.options.get("dashboard_url_path", "lovelace"))
        self.lock = threading.Lock()
        self.plans = {}
        self.state_lock = threading.Lock()
        self.state = {"busy": False, "phase": "Redo", "error": None, "last_result": None}
        self.last_operation = self.data / "last_operation.json"
        if self.last_operation.exists():
            try:
                self.state["last_result"] = json.loads(self.last_operation.read_text())
            except (OSError, ValueError):
                pass
        self.cache = self.data / "repository.git"
        self.journal = self.data / "rollback.json"
        self.ssh = self.data / "ssh"
        self.ssh.mkdir(mode=0o700, exist_ok=True)
        self.key = self.ssh / "id_ed25519"
        self.env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        self.env.pop("SUPERVISOR_TOKEN", None)
        # Only options from this application can configure Git; ignore inherited overrides.
        for name in list(self.env):
            if name.startswith("GIT_CONFIG_") and name not in {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"}:
                self.env.pop(name)
        self.env["GIT_SSH_COMMAND"] = " ".join(["ssh", "-F", "/dev/null", "-i", shlex.quote(str(self.key)),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=15", "-o", "UserKnownHostsFile=" + shlex.quote(str(self.ssh / "known_hosts"))])
        self.env["GIT_AUTHOR_NAME"] = self.env["GIT_COMMITTER_NAME"] = self.options.get("git_name", "Home Assistant")
        self.env["GIT_AUTHOR_EMAIL"] = self.env["GIT_COMMITTER_EMAIL"] = self.options.get("git_email", "ha@localhost")
        if self.journal.exists():
            journal = self.read_journal()
            if journal.get("phase") in {"applying", "restoring", "recovery_required"}:
                self.set_state(error="En avbruten uppdatering behöver återställas innan nästa synkning.", phase="Återställning krävs")
        self.cleanup_plans()

    def set_state(self, **fields):
        with self.state_lock:
            self.state.update(fields)
            if "last_result" in fields:
                atomic_write(self.last_operation, json.dumps(fields["last_result"]).encode())

    def status(self):
        with self.state_lock:
            state = dict(self.state)
        journal = self.read_journal() if self.journal.exists() else None
        state.update({"repository": self.options.get("repository"),
            "default_branch": self.options.get("default_branch", "main"),
            "push_branch": self.options.get("push_branch", "ha/updates"),
            "dashboard_sync": self.dashboard_sync,
            "dashboard_url_path": self.options.get("dashboard_url_path", "lovelace"),
            "dashboard_file": self.dashboard_file,
            "scope": self.scope.as_dict(),
            "public_key": self.key.with_suffix(".pub").read_text().strip() if self.key.with_suffix(".pub").exists() else None,
            "rollback": {k: journal.get(k) for k in ("phase", "branch", "commit", "backup", "created")} if journal else None})
        return state

    @contextmanager
    def operation(self, allow_recovery=False):
        if not self.lock.acquire(blocking=False):
            raise SyncError("En annan operation pågår. Vänta tills den är klar.")
        try:
            if self.journal.exists() and not allow_recovery and self.read_journal().get("phase") in {"applying", "restoring", "recovery_required"}:
                raise SyncError("Återställ den avbrutna uppdateringen först.")
            self.set_state(busy=True, error=None)
            yield
        except SyncError as err:
            self.set_state(error=str(err), phase="Stoppad")
            raise
        except Exception as err:
            self.set_state(error="Oväntat fel. Kontrollera tilläggets logg och återställningsstatus.", phase="Stoppad")
            raise SyncError("Oväntat fel. Kontrollera tilläggets logg och återställningsstatus.") from err
        finally:
            self.set_state(busy=False)
            self.lock.release()

    def run(self, *args, cwd=None, timeout=120, ok=(0,)):
        try:
            process = subprocess.run(args, cwd=cwd, env=self.env, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise SyncError("Git/SSH kunde inte slutföra operationen. Kontrollera åtkomst och nätverk.") from err
        if process.returncode not in ok:
            raise SyncError("Git/SSH nekade operationen. Kontrollera deploy key, branch och eventuella Git-konflikter.")
        return process.stdout.decode("utf-8", errors="replace").strip()

    def git(self, *args, cwd=None, **kwargs):
        return self.run("git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args, cwd=cwd, **kwargs)

    def setup_key(self):
        with self.operation():
            if not self.key.exists():
                self.run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "ha-git-sync", "-f", str(self.key))
            self.set_state(phase="SSH-nyckeln är redo")
            return self.status()

    def trust_github(self):
        if self.allow_local:
            return
        if not self.key.exists():
            raise SyncError("Skapa SSH-nyckeln och lägg till den som deploy key i GitHub först.")
        hosts = self.ssh / "known_hosts"
        if not hosts.exists():
            scanned = self.run("ssh-keyscan", "-T", "15", "-t", "ed25519", "github.com", timeout=30)
            candidate = self.ssh / "known_hosts.pending"
            atomic_write(candidate, (scanned + "\n").encode())
            try:
                fingerprint = self.run("ssh-keygen", "-lf", str(candidate), "-E", "sha256")
                if not fingerprint or any(line.split()[1] != GITHUB_FINGERPRINT for line in fingerprint.splitlines()):
                    raise SyncError("GitHubs SSH-fingeravtryck stämmer inte. Anslutningen stoppades.")
                os.replace(candidate, hosts)
            finally:
                candidate.unlink(missing_ok=True)

    def refresh(self):
        self.set_state(phase="Hämtar GitHub-brancher")
        self.trust_github()
        if not self.cache.exists():
            self.git("init", "--bare", str(self.cache))
            self.git("remote", "add", "origin", self.repository, cwd=self.cache)
        else:
            self.git("remote", "set-url", "origin", self.repository, cwd=self.cache)
        self.git("fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*", cwd=self.cache)
        return self.git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=self.cache).splitlines()

    def branches(self):
        with self.operation():
            branches = self.refresh()
            self.set_state(phase="Redo")
            return branches

    @staticmethod
    def validate_dashboard_file(name):
        if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name or re.search(r"[\x00-\x1f\x7f]", name):
            raise SyncError("Ange en YAML-fil under dashboards/, exempelvis dashboards/overview.yaml.")
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) < 2 or path.parts[0] != "dashboards" or path.suffix.lower() not in {".yaml", ".yml"} or any(part.startswith(".") or "secret" in part.lower() for part in path.parts):
            raise SyncError("Dashboardfilen måste vara en säker, relativ YAML-sökväg under dashboards/.")
        return path.as_posix()

    def configure_dashboard(self, enabled, url_path, repo_file):
        if not isinstance(enabled, bool) or not isinstance(url_path, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", url_path):
            raise SyncError("Välj en giltig dashboard och synkningsinställning.")
        repo_file = self.validate_dashboard_file(repo_file)
        with self.operation():
            if enabled:
                available = self.ha.dashboards()
                selected = next((item for item in available if item.get("url_path") == url_path), None)
                if selected is None and url_path != "lovelace":
                    raise SyncError("Dashboarden finns inte. Hämta dashboardlistan på nytt.")
                if selected and selected.get("mode") != "storage":
                    raise SyncError("Välj en dashboard som redigeras i HA:s gränssnitt.")
                original = self.ha.dashboard_path
                self.ha.dashboard_path = url_path
                try:
                    parse_dashboard(dashboard_bytes(self.ha.dashboard()))
                finally:
                    self.ha.dashboard_path = original
            settings = {"dashboard_sync": enabled, "dashboard_url_path": url_path, "dashboard_file": repo_file}
            atomic_write(self.dashboard_settings, json.dumps(settings).encode())
            self.options.update(settings)
            self.dashboard_sync = enabled
            self.dashboard_file = repo_file
            self.ha.dashboard_path = url_path
            # A saved preview may target another dashboard even if its content is identical.
            for plan in self.plans.values():
                shutil.rmtree(plan["work"], ignore_errors=True)
            self.plans.clear()
            self.set_state(phase="Dashboardinställningarna sparade")
            return settings

    def validate_branch(self, branch):
        if not isinstance(branch, str) or not branch or len(branch) > 200 or branch.startswith("-"):
            raise SyncError("Ogiltigt branchnamn.")
        self.git("check-ref-format", "--branch", branch)
        return branch

    def configure_scope(self, includes, excludes):
        scope = Scope(includes, excludes)
        with self.operation():
            # Validate existing selected paths, including parent links, before saving.
            inventory(self.config_root, scope, [self.dashboard_file] if self.dashboard_sync else [])
            atomic_write(self.scope_settings, json.dumps(scope.as_dict()).encode())
            self.scope = scope
            for plan in self.plans.values():
                shutil.rmtree(plan["work"], ignore_errors=True)
            self.plans.clear()
            self.set_state(phase="Filurvalet sparat")
            return scope.as_dict()

    def scope_catalog(self):
        with self.operation():
            entries = {}
            for parent, directories, names in os.walk(self.config_root, followlinks=False):
                for directory in directories:
                    name = (Path(parent) / directory).relative_to(self.config_root).as_posix() + "/"
                    entries[name] = {"path": name, "directory": True, "exists": True, "blocked": not eligible(name, True) or (Path(parent) / directory).is_symlink()}
                directories[:] = [d for d in directories if eligible((Path(parent) / d).relative_to(self.config_root).as_posix(), True) and not (Path(parent) / d).is_symlink()]
                for filename in names:
                    name = (Path(parent) / filename).relative_to(self.config_root).as_posix()
                    entries[name] = {"path": name, "directory": False, "exists": True, "blocked": not eligible(name) or (Path(parent) / filename).is_symlink()}
                if len(entries) > 2000:
                    raise SyncError("För många filer att visa. Använd extra sökvägar eller mindre mappar i filurvalet.")
            for rule in self.scope.includes:
                entries.setdefault(rule, {"path": rule, "directory": rule.endswith("/"), "exists": False})
            self.set_state(phase="Filurvalet hämtat")
            return {"entries": [entries[name] for name in sorted(entries)], **self.scope.as_dict()}

    def current(self):
        result = inventory(self.config_root, self.scope, [self.dashboard_file] if self.dashboard_sync else [])
        if self.dashboard_sync:
            result[self.dashboard_file] = dashboard_bytes(self.ha.dashboard())
        return result

    def checkout(self, branch, mode):
        self.validate_branch(branch)
        branches = self.refresh()
        source = branch
        if branch not in branches:
            if mode != "push":
                raise SyncError("Den valda branchen finns inte på GitHub.")
            source = self.validate_branch(self.options.get("default_branch", "main"))
            if source not in branches:
                raise SyncError("Basbranchen finns inte på GitHub.")
        sha = self.git("rev-parse", "refs/heads/" + source, cwd=self.cache)
        plan_id = uuid.uuid4().hex
        work = self.data / "plans" / plan_id
        work.parent.mkdir(mode=0o700, exist_ok=True)
        self.git("clone", "--no-hardlinks", "--no-checkout", str(self.cache), str(work))
        self.git("checkout", "--detach", sha, cwd=work)
        self.git("remote", "set-url", "origin", self.repository, cwd=work)
        return plan_id, work, sha, branch not in branches

    def cleanup_plans(self):
        folder = self.data / "plans"
        if folder.exists():
            for child in folder.iterdir():
                if child.is_dir() and time.time() - child.stat().st_mtime > 900:
                    shutil.rmtree(child)
        self.plans = {k: v for k, v in self.plans.items() if time.time() - v["created"] < 900}

    def preview(self, mode, branch, allow_deletions=False):
        if mode not in {"push", "pull"}:
            raise SyncError("Ogiltig operation.")
        if not isinstance(allow_deletions, bool):
            raise SyncError("Ogiltigt val för borttagningar.")
        with self.operation():
            self.cleanup_plans()
            plan_id, work, sha, new_branch = self.checkout(branch, mode)
            try:
                remote = inventory(work, self.scope, [self.dashboard_file] if self.dashboard_sync else [])
                if self.dashboard_sync:
                    dashboard_path = self.options.get("dashboard_url_path", "lovelace")
                    for item in self.ha.dashboards():
                        if item.get("url_path") == dashboard_path and item.get("mode") != "storage":
                            raise SyncError("Den valda dashboarden är inte redigerbar i storage-läge.")
                    dashboard = safe_path(work, self.dashboard_file)
                    if dashboard.exists():
                        remote[self.dashboard_file] = dashboard_bytes(parse_dashboard(read_file(dashboard)))
                    elif mode == "pull":
                        raise SyncError(f"Branchen saknar {self.dashboard_file}.")
                local = self.current()
                if mode == "pull" and self.scope.accepts("configuration.yaml") and "configuration.yaml" not in remote:
                    raise SyncError("configuration.yaml saknas i branchen. Uppdateringen stoppades.")
                desired = canonical_yaml(local) if mode == "push" else remote
                kept_local = []
                if mode == "pull" and not allow_deletions:
                    kept_local = sorted(local.keys() - remote.keys())
                    desired = {**{name: local[name] for name in kept_local}, **remote}
                if self.scope.accepts("configuration.yaml") and "configuration.yaml" not in desired:
                    raise SyncError("configuration.yaml saknas. Uppdateringen stoppades.")
                validate_yaml(desired)
                sensitive = scan_secrets(desired)
                if sensitive:
                    raise SyncError("Misstänkta hemligheter i: " + ", ".join(sensitive) + ". Flytta dem till secrets innan synkning.")
                before = remote if mode == "push" else local
                before_normal = canonical_yaml(before)
                desired_normal = canonical_yaml(desired)
                change_list = changes(before_normal, desired_normal)
                for change in change_list:
                    name = change["path"]
                    change["diff"] = text_diff(name, before_normal.get(name, b""), desired_normal.get(name, b""))
                self.plans[plan_id] = {"created": time.time(), "mode": mode, "branch": branch,
                    "sha": sha, "work": work, "new_branch": new_branch, "local_digest": digest(local),
                    "desired": desired, "changes": change_list}
                result = {"id": plan_id, "mode": mode, "branch": branch, "commit": sha,
                    "new_branch": new_branch, "changes": change_list, "expires_in": 900,
                    "dashboard_sync": self.dashboard_sync, "kept_local": kept_local, "allow_deletions": allow_deletions}
                self.set_state(phase="Granskning klar")
                return result
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise

    def consume_plan(self, plan_id, mode):
        plan = self.plans.pop(plan_id, None)
        if plan is None or plan["mode"] != mode or time.time() - plan["created"] >= 900:
            raise SyncError("Förhandsgranskningen har gått ut. Granska på nytt.")
        if digest(self.current()) != plan["local_digest"]:
            shutil.rmtree(plan["work"], ignore_errors=True)
            raise SyncError("HA-filer eller dashboard ändrades efter granskningen. Granska på nytt.")
        return plan

    def push(self, plan_id, message):
        if not isinstance(message, str) or not message.strip() or len(message) > 500:
            raise SyncError("Ange ett commit-meddelande på högst 500 tecken.")
        with self.operation():
            plan = self.consume_plan(plan_id, "push")
            try:
                if not plan["changes"]:
                    if plan["new_branch"]:
                        self.ha.check()
                        self.git("push", "--force-with-lease=refs/heads/" + plan["branch"] + ":", "origin",
                            plan["sha"] + ":refs/heads/" + plan["branch"], cwd=plan["work"])
                        result = {"changed": False, "branch_created": True, "branch": plan["branch"], "commit": plan["sha"]}
                        self.set_state(phase="Branchen skapad", last_result={"operation": "push", **result})
                        return result
                    self.set_state(phase="Inga ändringar att pusha")
                    return {"changed": False}
                self.set_state(phase="Kontrollerar HA-konfigurationen")
                self.ha.check()
                if digest(self.current()) != plan["local_digest"]:
                    raise SyncError("HA ändrades under kontrollen. Granska på nytt.")
                for change in plan["changes"]:
                    path = safe_path(plan["work"], change["path"])
                    if change["path"] in plan["desired"]:
                        atomic_write(path, plan["desired"][change["path"]], 0o644)
                    else:
                        path.unlink(missing_ok=True)
                # Explicit paths prevent staging documentation, secrets or the add-on itself.
                names = [change["path"] for change in plan["changes"]]
                self.git("add", "-A", "--", *names, cwd=plan["work"])
                staged = self.git("diff", "--cached", "--name-only", "-z", cwd=plan["work"])
                if set(filter(None, staged.split("\0"))) != set(names):
                    raise SyncError("Git index stämmer inte med granskningen. Kontrollera repots ignore-regler och granska på nytt.")
                self.git("commit", "-m", message.strip(), cwd=plan["work"])
                commit = self.git("rev-parse", "HEAD", cwd=plan["work"])
                self.set_state(phase="Pushar till GitHub")
                # A lease prevents even a fast-forward overwrite of a concurrently moved branch.
                expected = "" if plan["new_branch"] else plan["sha"]
                self.git("push", "--force-with-lease=refs/heads/" + plan["branch"] + ":" + expected,
                    "origin", commit + ":refs/heads/" + plan["branch"], cwd=plan["work"])
                result = {"changed": True, "branch": plan["branch"], "commit": commit}
                self.set_state(phase="Push klar", last_result={"operation": "push", **result})
                return result
            finally:
                shutil.rmtree(plan["work"], ignore_errors=True)

    def write_journal(self, journal):
        atomic_write(self.journal, json.dumps(journal, ensure_ascii=False).encode())

    def read_journal(self):
        try:
            return json.loads(self.journal.read_text())
        except (OSError, ValueError) as err:
            raise SyncError("Återställningsjournalen kan inte läsas. Bevara /data och kontrollera loggen.") from err

    def snapshot(self, plan, backup):
        folder = self.data / "snapshots" / uuid.uuid4().hex
        folder.mkdir(parents=True, mode=0o700)
        journal = {"phase": "prepared", "branch": plan["branch"], "commit": plan["sha"],
            "backup": backup, "created": time.time(), "snapshot": str(folder), "paths": [],
            "dashboard_enabled": self.dashboard_sync,
            "dashboard_path": self.options.get("dashboard_url_path", "lovelace")}
        for change in plan["changes"]:
            name = change["path"]
            if self.dashboard_sync and name == self.dashboard_file:
                continue
            path = safe_path(self.config_root, name)
            exists = path.exists()
            journal["paths"].append({"name": name, "exists": exists, "mode": path.stat().st_mode & 0o777 if exists else 0o600})
            if exists:
                atomic_write(safe_path(folder, name), read_file(path))
        if self.dashboard_sync and any(c["path"] == self.dashboard_file for c in plan["changes"]):
            journal["dashboard"] = self.ha.dashboard()
        self.write_journal(journal)
        return journal

    def pull(self, plan_id):
        with self.operation():
            plan = self.consume_plan(plan_id, "pull")
            journal = None
            try:
                if not plan["changes"]:
                    self.set_state(phase="HA stämmer redan med branchen")
                    return {"changed": False}
                self.set_state(phase="Kontrollerar nuvarande HA-konfiguration")
                self.ha.check()
                self.set_state(phase="Tar backup av Home Assistant; inväntar färdig backup")
                backup = self.ha.backup()
                if digest(self.current()) != plan["local_digest"]:
                    raise SyncError("HA ändrades under backupen. Inga filer uppdaterades. Granska på nytt.")
                journal = self.snapshot(plan, backup)
                if digest(self.current()) != plan["local_digest"]:
                    raise SyncError("HA ändrades under förberedelsen. Inga filer uppdaterades. Granska på nytt.")
                journal["phase"] = "applying"
                self.write_journal(journal)
                self.set_state(phase="Läser in filer från GitHub")
                for change in plan["changes"]:
                    name = change["path"]
                    if self.dashboard_sync and name == self.dashboard_file:
                        continue
                    path = safe_path(self.config_root, name)
                    if name in plan["desired"]:
                        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
                        atomic_write(path, plan["desired"][name], mode)
                    else:
                        path.unlink(missing_ok=True)
                self.set_state(phase="Kontrollerar uppdaterad HA-konfiguration")
                self.ha.check()
                if "dashboard" in journal:
                    self.set_state(phase="Uppdaterar dashboard via HA:s API")
                    self.ha.save_dashboard(parse_dashboard(plan["desired"][self.dashboard_file]))
                journal["phase"] = "applied"
                self.write_journal(journal)
                try:
                    self.prune_snapshots()
                except OSError:
                    # Cleanup must not turn an already successful apply into a failed update.
                    pass
                result = {"changed": True, "branch": plan["branch"], "commit": plan["sha"], "backup": backup, "restart_required": True}
                self.set_state(phase="Inläsning klar. Starta om HA när du är redo.", last_result={"operation": "pull", **result})
                return result
            except Exception as err:
                if journal and journal.get("phase") == "applying":
                    self.set_state(phase="Uppdateringen misslyckades. Återställer originalen.")
                    try:
                        self.restore_journal(journal)
                    except Exception as recovery_error:
                        journal["phase"] = "recovery_required"
                        self.write_journal(journal)
                        raise SyncError("Uppdateringen och återställningen misslyckades. Använd Återställ eller HA-backupen.") from recovery_error
                    raise SyncError("Uppdateringen misslyckades. Originalfiler och dashboard har återställts.") from err
                raise
            finally:
                shutil.rmtree(plan["work"], ignore_errors=True)

    def restore_journal(self, journal):
        folder = Path(journal["snapshot"])
        if not folder.resolve().is_relative_to((self.data / "snapshots").resolve()):
            raise SyncError("Ogiltig återställningskatalog.")
        journal["phase"] = "restoring"
        self.write_journal(journal)

        for item in journal["paths"]:
            if not eligible(item["name"]):
                raise SyncError("Journalen innehåller en fil utanför fillistan.")
            path = safe_path(self.config_root, item["name"])
            if item["exists"]:
                atomic_write(path, read_file(safe_path(folder, item["name"])), item["mode"])
            else:
                path.unlink(missing_ok=True)
        if "dashboard" in journal:
            # Recover the original dashboard even if the selected option changed later.
            original_path = getattr(self.ha, "dashboard_path", None)
            self.ha.dashboard_path = journal["dashboard_path"]
            try:
                self.ha.save_dashboard(journal["dashboard"])
            finally:
                self.ha.dashboard_path = original_path
        self.ha.check()
        journal["phase"] = "restored"
        self.write_journal(journal)

    def prune_snapshots(self):
        """Retain the active recovery point and recent owned snapshots only."""
        root = self.data / "snapshots"
        current = Path(self.read_journal()["snapshot"])
        retention = max(1, min(20, int(self.options.get("snapshot_retention", 3))))
        folders = sorted((p for p in root.iterdir() if not p.is_symlink() and p.is_dir() and re.fullmatch(r"[0-9a-f]{32}", p.name)),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        keep = {current}
        for folder in folders:
            if len(keep) < retention:
                keep.add(folder)
        for folder in folders:
            if folder not in keep:
                shutil.rmtree(folder, ignore_errors=True)

    def restore(self):
        with self.operation(allow_recovery=True):
            if not self.journal.exists():
                raise SyncError("Ingen uppdatering finns att återställa.")
            journal = self.read_journal()
            self.set_state(phase="Återställer senaste uppdateringen")
            try:
                self.restore_journal(journal)
            except Exception:
                journal["phase"] = "recovery_required"
                self.write_journal(journal)
                raise SyncError("Återställningen är inte klar. Originalen finns kvar; använd HA-backupen om Core inte går att kontrollera.")
            self.set_state(phase="Återställd. Starta om HA för att aktivera originalkonfigurationen.", last_result={"operation": "restore"})
            return {"restored": True}

    def restart(self):
        with self.operation():
            self.set_state(phase="Kontrollerar och startar om Home Assistant")
            self.ha.check()
            self.ha.restart()
            self.set_state(phase="Home Assistant startas om")
            return {"restarted": True}
