"""Supervisor backup/check APIs and Lovelace's supported WebSocket commands."""

import json
import os
import urllib.error
import urllib.request

import websocket

from files import SyncError


class HomeAssistant:
    def __init__(self, dashboard_path="lovelace", token=None, timeout=1800):
        self.token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
        self.dashboard_path = dashboard_path
        self.timeout = timeout

    def request(self, path, body=None, timeout=None):
        if not self.token:
            raise SyncError("Supervisor-token saknas. Kör tjänsten som ett HA-tillägg.")
        request = urllib.request.Request("http://supervisor" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            # Local Supervisor traffic must not go through an external HTTP proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=timeout or self.timeout) as response:
                result = json.load(response)
            if result.get("result") != "ok":
                raise SyncError(f"HA kunde inte slutföra {path}. Kontrollera Supervisor-loggen.")
            return result.get("data", {})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            raise SyncError(f"Ingen godkänd respons från HA för {path}. Inga fler steg körs.") from err

    def backup(self):
        # Synchronous request: Supervisor only returns slug once the backup is complete.
        import datetime
        name = "Git Sync " + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        data = self.request("/backups/new/partial", {"name": name, "homeassistant": True, "background": False})
        slug = data.get("slug")
        if not slug or not isinstance(slug, str):
            raise SyncError("Backupen är inte bekräftat klar. Uppdateringen stoppades.")
        info = self.request(f"/backups/{slug}/info", timeout=30)
        if not info.get("homeassistant"):
            raise SyncError("Backupen innehåller inte Home Assistant. Uppdateringen stoppades.")
        return slug

    def check(self):
        self.request("/core/check", {}, timeout=300)

    def restart(self):
        self.request("/core/restart", {}, timeout=300)

    def command(self, command, **fields):
        if not self.token:
            raise SyncError("Supervisor-token saknas.")
        connection = None
        try:
            connection = websocket.create_connection("ws://supervisor/core/websocket", timeout=30,
                header=["Authorization: Bearer " + self.token], http_no_proxy=["supervisor"], suppress_origin=True)
            greeting = json.loads(connection.recv())
            if greeting.get("type") != "auth_required":
                raise SyncError("Oväntat svar från HA:s dashboard-API.")
            connection.send(json.dumps({"type": "auth", "access_token": self.token}))
            if json.loads(connection.recv()).get("type") != "auth_ok":
                raise SyncError("Dashboard-API:t nekade åtkomst.")
            connection.send(json.dumps({"id": 1, "type": command, **fields}))
            result = json.loads(connection.recv())
            if result.get("id") != 1 or not result.get("success"):
                raise SyncError("Dashboard-API:t kunde inte utföra kommandot. Kontrollera vald dashboard.")
            return result.get("result")
        except (websocket.WebSocketException, OSError, ValueError) as err:
            raise SyncError("Kunde inte nå HA:s dashboard-API.") from err
        finally:
            if connection is not None:
                connection.close()

    def dashboard(self):
        return self.command("lovelace/config", url_path=None if self.dashboard_path == "lovelace" else self.dashboard_path or None, force=True)

    def save_dashboard(self, config):
        self.command("lovelace/config/save", url_path=None if self.dashboard_path == "lovelace" else self.dashboard_path or None, config=config)

    def dashboards(self):
        return self.command("lovelace/dashboards/list")
