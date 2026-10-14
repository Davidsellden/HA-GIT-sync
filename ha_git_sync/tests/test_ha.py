"""Check actual Supervisor request contracts, including backup completion gates."""

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from files import SyncError
from ha import HomeAssistant


class HATests(unittest.TestCase):
    def response(self, data):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps(data).encode())
        return response

    @patch("ha.urllib.request.build_opener")
    def test_completed_backup_is_verified_before_return(self, build_opener):
        opener = build_opener.return_value
        opener.open.side_effect = [self.response({"result": "ok", "data": {"slug": "abc", "job_id": "job"}}),
                                  self.response({"result": "ok", "data": {"homeassistant": "2026.10.1"}})]
        ha = HomeAssistant(token="test-only")
        self.assertEqual(ha.backup(), "abc")
        request = opener.open.call_args_list[0].args[0]
        self.assertEqual(request.full_url, "http://supervisor/backups/new/partial")
        body = json.loads(request.data)
        self.assertIs(body["background"], False)
        self.assertIs(body["homeassistant"], True)
        self.assertEqual(opener.open.call_args_list[1].args[0].full_url, "http://supervisor/backups/abc/info")

    @patch("ha.urllib.request.build_opener")
    def test_background_job_without_slug_cannot_allow_apply(self, build_opener):
        build_opener.return_value.open.return_value = self.response({"result": "ok", "data": {"job_id": "job"}})
        with self.assertRaisesRegex(SyncError, "inte bekräftat klar"):
            HomeAssistant(token="test-only").backup()

    @patch("ha.urllib.request.build_opener")
    def test_backup_without_ha_content_rejected(self, build_opener):
        build_opener.return_value.open.side_effect = [self.response({"result": "ok", "data": {"slug": "abc"}}),
                                                     self.response({"result": "ok", "data": {"homeassistant": None}})]
        with self.assertRaisesRegex(SyncError, "innehåller inte"):
            HomeAssistant(token="test-only").backup()

    @patch("ha.urllib.request.build_opener")
    def test_error_response_does_not_expose_supervisor_message(self, build_opener):
        build_opener.return_value.open.return_value = self.response({"result": "error", "message": "password=private"})
        with self.assertRaises(SyncError) as error:
            HomeAssistant(token="test-only").check()
        self.assertNotIn("private", str(error.exception))

    @patch("ha.websocket.create_connection")
    def test_websocket_auth_and_dashboard_commands(self, create_connection):
        connection = create_connection.return_value
        connection.recv.side_effect = [json.dumps({"type": "auth_required"}), json.dumps({"type": "auth_ok"}),
                                      json.dumps({"id": 1, "success": True, "result": {"views": []}})]
        ha = HomeAssistant(token="test-only", dashboard_path="lovelace")
        self.assertEqual(ha.dashboard(), {"views": []})
        payload = json.loads(connection.send.call_args_list[1].args[0])
        self.assertEqual(payload["type"], "lovelace/config")
        self.assertIsNone(payload["url_path"])
        connection.close.assert_called_once()

    @patch("ha.websocket.create_connection")
    def test_dashboard_save_denied_is_reported_and_connection_closed(self, create_connection):
        connection = create_connection.return_value
        connection.recv.side_effect = [json.dumps({"type": "auth_required"}), json.dumps({"type": "auth_ok"}),
                                      json.dumps({"id": 1, "success": False})]
        with self.assertRaises(SyncError):
            HomeAssistant(token="test-only", dashboard_path="dashboard-overview").save_dashboard({"views": []})
        payload = json.loads(connection.send.call_args_list[1].args[0])
        self.assertEqual(payload["type"], "lovelace/config/save")
        self.assertEqual(payload["url_path"], "dashboard-overview")
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
