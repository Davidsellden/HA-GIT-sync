"""Allowlisted, bounded file snapshots. Never follow links into secrets or storage."""

from __future__ import annotations

import hashlib
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

import yaml


class SyncError(Exception):
    """An error safe to present without dumping commands, tokens or file contents."""


ROOT_FILES = {"configuration.yaml", "automations.yaml", "scripts.yaml", "scenes.yaml"}
YAML_DIRS = {"packages", "themes", "blueprints"}
ASSET_SUFFIXES = {".svg", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}
DEFAULT_DASHBOARD_FILE = "dashboards/dashboard.yaml"
LEGACY_DASHBOARD_FILE = "dashboards/hemma.yaml"
MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
DEFAULT_INCLUDES = sorted(ROOT_FILES) + ["packages/", "themes/", "blueprints/", "www/"]
FILE_SUFFIXES = ASSET_SUFFIXES | {".yaml", ".yml", ".json", ".txt", ".md", ".csv", ".py", ".sh", ".jinja", ".j2", ".xml", ".conf", ".ini"}
PROTECTED_DIRS = {"custom_components", "zigbee2mqtt", "deps", "tts", "backup", "backups", "__pycache__"}


def eligible(name, directory=False):
    if not isinstance(name, str) or not name or "\\" in name or re.search(r"[\x00-\x1f\x7f]", name):
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(p.startswith(".") or "secret" in p.lower() or p in PROTECTED_DIRS for p in path.parts):
        return False
    if path.parts[:2] == ("www", "community") or path.name in {"ip_bans.yaml", "known_devices.yaml"} or ".log" in path.name.lower():
        return False
    return bool(path.parts) and (directory or path.suffix.lower() in FILE_SUFFIXES)


class Scope:
    def __init__(self, includes=None, excludes=None, legacy=False):
        self.includes = self.normalize(DEFAULT_INCLUDES if includes is None else includes)
        self.excludes = self.normalize([] if excludes is None else excludes)
        self.legacy = legacy

    @staticmethod
    def normalize(rules):
        if not isinstance(rules, list) or len(rules) > 200:
            raise SyncError("Välj högst 200 filsökvägar eller mappar.")
        result = set()
        for rule in rules:
            directory = isinstance(rule, str) and rule.endswith("/")
            if not eligible(rule, directory):
                raise SyncError("En vald sökväg är skyddad eller inte en tillåten konfigurationsfil.")
            result.add(PurePosixPath(rule).as_posix() + ("/" if directory else ""))
        return sorted(result)

    @staticmethod
    def matches(name, rule):
        return name.startswith(rule) if rule.endswith("/") else name == rule

    def accepts(self, name):
        return eligible(name) and (not self.legacy or managed(name)) and any(self.matches(name, rule) for rule in self.includes) and not any(self.matches(name, rule) for rule in self.excludes)

    def as_dict(self):
        return {"includes": self.includes, "excludes": self.excludes}


def managed(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in {".", ".."} or p.startswith(".") for p in path.parts):
        return False
    if "\\" in name or any("secret" in p.lower() for p in path.parts):
        return False
    if name in ROOT_FILES:
        return True
    if len(path.parts) < 2:
        return False
    if path.parts[0] in YAML_DIRS:
        return path.suffix.lower() in {".yaml", ".yml"}
    return path.parts[0] == "www" and path.parts[1] != "community" and path.suffix.lower() in ASSET_SUFFIXES


def safe_path(root: Path, name: str) -> Path:
    """Also check ancestor symlinks, including links whose target is missing."""
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or "\\" in name or any(p in {".", ".."} for p in parts):
        raise SyncError("Ogiltig filsökväg.")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SyncError(f"Symbolisk länk tillåts inte: {name}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise SyncError("Filsökvägen ligger utanför konfigurationskatalogen.")
    return current


def inventory(root: Path, scope=None, skip_paths=()) -> dict[str, bytes]:
    if scope is not None:
        result = {}
        for rule in scope.includes:
            name = rule.rstrip("/")
            start = safe_path(root, name)
            if not start.exists():
                continue
            if rule.endswith("/"):
                if not start.is_dir():
                    raise SyncError(f"Förväntade en katalog: {name}")
                for parent, directories, names in os.walk(start, followlinks=False):
                    directories[:] = [d for d in directories if eligible((Path(parent) / d).relative_to(root).as_posix(), True)]
                    for filename in names:
                        candidate = (Path(parent) / filename).relative_to(root).as_posix()
                        if candidate not in skip_paths and scope.accepts(candidate):
                            result[candidate] = read_file(safe_path(root, candidate))
                    for d in directories:
                        safe_path(root, (Path(parent) / d).relative_to(root).as_posix())
            elif name not in skip_paths and scope.accepts(name):
                result[name] = read_file(start)
        if sum(map(len, result.values())) > MAX_TOTAL:
            raise SyncError("De valda filerna överstiger 64 MB.")
        return result
    result: dict[str, bytes] = {}
    for folder in [*sorted(YAML_DIRS), "www"]:
        start = safe_path(root, folder)
        if not start.exists():
            continue
        if not start.is_dir():
            raise SyncError(f"Förväntade en katalog: {folder}")
        for parent, directories, names in os.walk(start, followlinks=False):
            directories[:] = [d for d in directories if not d.startswith(".") and "secret" not in d.lower() and not (folder == "www" and Path(parent) == start and d == "community")]
            for d in directories:
                safe_path(root, (Path(parent) / d).relative_to(root).as_posix())
            for filename in names:
                name = (Path(parent) / filename).relative_to(root).as_posix()
                if managed(name):
                    result[name] = read_file(safe_path(root, name))
    for name in sorted(ROOT_FILES):
        path = safe_path(root, name)
        if path.exists():
            result[name] = read_file(path)
    if sum(map(len, result.values())) > MAX_TOTAL:
        raise SyncError("De valda filerna överstiger 64 MB.")
    return result


def read_file(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise SyncError(f"Filen är inte en vanlig fil eller överstiger 10 MB: {path.name}")
    return path.read_bytes()


def digest(data: dict[str, bytes]) -> str:
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(data.items())}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def changes(before: dict[str, bytes], after: dict[str, bytes]) -> list[dict]:
    return [{"path": name, "action": "ny" if name not in before else "tas bort" if name not in after else "ändrad",
             "size": len(after.get(name, b""))}
            for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]


def text_diff(name: str, before: bytes, after: bytes) -> str | None:
    if PurePosixPath(name).suffix.lower() not in (FILE_SUFFIXES - (ASSET_SUFFIXES - {".svg", ".css", ".js"})) or max(len(before), len(after)) > 65536:
        return None
    try:
        # Removed credentials must not leak through a preview of an otherwise safe target.
        if (before and scan_secrets({name: before})) or (after and scan_secrets({name: after})):
            return "Skillnaden döljs eftersom filen kan innehålla hemligheter. Granska lokalt."
        lines = list(difflib.unified_diff(before.decode("utf-8").splitlines(), after.decode("utf-8").splitlines(),
            fromfile="före/" + name, tofile="efter/" + name, lineterm=""))
        return "\n".join(lines[:250]) + ("\n… skillnaden är förkortad." if len(lines) > 250 else "")
    except (yaml.YAMLError, SyncError, UnicodeError, ValueError, TypeError, RecursionError):
        return "Skillnaden kan inte visas säkert. Granska filen lokalt."


def canonical_yaml(data: dict[str, bytes]) -> dict[str, bytes]:
    """Avoid CRLF/EOF-only churn, preserving the meaning of block scalars."""
    result = dict(data)
    for name, content in data.items():
        if PurePosixPath(name).suffix.lower() not in {".yaml", ".yml"}:
            continue
        normalized = content.replace(b"\r\n", b"\n")
        candidate = normalized.rstrip(b"\n") + b"\n" if normalized else b""
        try:
            if yaml.load(normalized, Loader=HALoader) == yaml.load(candidate, Loader=HALoader):
                normalized = candidate
        except (yaml.YAMLError, SyncError, UnicodeError, ValueError, TypeError, RecursionError):
            pass
        result[name] = normalized
    return result


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".git-sync-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(filename, mode)
        os.replace(filename, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


class HALoader(yaml.SafeLoader):
    """Parse HA tags without resolving secrets, includes, or executing constructors."""


def ha_tag(loader, suffix, node):
    if suffix not in {"secret", "input", "include", "include_dir_list", "include_dir_named", "include_dir_merge_list", "include_dir_merge_named"}:
        raise SyncError("Okänd YAML-tagg.")
    return {"__ha_tag__": suffix, "value": loader.construct_scalar(node)}


def unique_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise SyncError("YAML innehåller dubbla nycklar.")
        seen.add(key)
    loader.flatten_mapping(node)
    return loader.construct_mapping(node, deep=deep)


HALoader.add_multi_constructor("!", ha_tag)
HALoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def validate_yaml(data: dict[str, bytes]) -> None:
    for name, content in data.items():
        if PurePosixPath(name).suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            parsed = yaml.load(content.decode("utf-8"), Loader=HALoader)
            if name == "configuration.yaml" and not isinstance(parsed, dict):
                raise SyncError("configuration.yaml måste innehålla en YAML-mappning.")
            if name.startswith("packages/") and not isinstance(parsed, dict):
                raise SyncError("Packages måste innehålla YAML-mappningar.")
        except (yaml.YAMLError, UnicodeError, TypeError, ValueError) as err:
            raise SyncError(f"Ogiltig YAML: {name}. Kontrollera filen lokalt.") from err


SENSITIVE_KEYS = re.compile(r"(?:^|[_-])(?:password|passwd|token|api_key|access_key|client_secret|network_key|private_key)$", re.I)
SENSITIVE_TEXT = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?i:Bearer)\s+[A-Za-z0-9._-]{20,}|(?i:https?)://[^/\s:@]+:[^/\s@]+@)")
SENSITIVE_LITERAL = re.compile(rb"(?im)\b(?:[A-Za-z0-9_-]*_)?(?:password|passwd|token|api_key|client_secret|network_key|private_key)\s*[:=]\s*['\"][^'\"\r\n]+['\"]")
SENSITIVE_CONFIG = re.compile(rb"(?im)^\s*(?:[A-Za-z0-9_-]*_)?(?:password|passwd|token|api_key|client_secret|network_key|private_key)\s*[:=]\s*[^\s#;\r\n]+")


def scan_secrets(data: dict[str, bytes]) -> list[str]:
    """Conservative heuristic: report file names only, never secret values."""
    found = []
    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if SENSITIVE_KEYS.search(str(key)) and child not in (None, ""):
                    if not (isinstance(child, dict) and child.get("__ha_tag__") == "secret"):
                        return True
                if inspect(child):
                    return True
        elif isinstance(value, list):
            return any(inspect(item) for item in value)
        return False
    for name, content in data.items():
        if (b"-----BEGIN " in content and b"PRIVATE KEY-----" in content) or SENSITIVE_TEXT.search(content):
            found.append(name)
            continue
        suffix = PurePosixPath(name).suffix.lower()
        if suffix not in {".yaml", ".yml", ".json"} and (SENSITIVE_LITERAL.search(content) or (suffix in {".ini", ".conf", ".txt"} and SENSITIVE_CONFIG.search(content))):
            found.append(name)
            continue
        if suffix == ".json":
            try:
                if inspect(json.loads(content)):
                    found.append(name)
            except (ValueError, UnicodeError) as err:
                raise SyncError(f"Ogiltig JSON: {name}. Granska filen lokalt.") from err
        elif suffix in {".yaml", ".yml"} and inspect(yaml.load(content, Loader=HALoader)):
            found.append(name)
    return found


def dashboard_bytes(config: dict) -> bytes:
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode("utf-8")


def parse_dashboard(content: bytes) -> dict:
    try:
        config = yaml.safe_load(content)
        if not isinstance(config, dict) or not (isinstance(config.get("views"), list) or isinstance(config.get("strategy"), dict)):
            raise ValueError("Expected views or strategy")
        return config
    except (yaml.YAMLError, ValueError, UnicodeError) as err:
        raise SyncError("Dashboardens YAML är ogiltig.") from err
