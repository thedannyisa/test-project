#!/usr/bin/env python3
"""Tests for the local Cursor office server."""

from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import server


class FakeCursor(BaseHTTPRequestHandler):
    seen_auth: list[str] = []
    mode = "ok"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self.seen_auth.append(self.headers.get("Authorization") or "")
        if self.mode == "deny":
            body = json.dumps({"message": "bad key"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "cursor=page-2" in self.path:
            payload = {
                "items": [
                    {
                        "id": "bc-old",
                        "name": "<img src=x onerror=alert(1)>",
                        "status": "ARCHIVED",
                        "url": "https://cursor.com/agents/bc-old",
                        "updatedAt": "2026-10-01T00:00:00.000Z",
                    }
                ]
            }
        else:
            payload = {
                "items": [
                    {
                        "id": "bc-busy",
                        "name": "Пишет тесты",
                        "status": "ACTIVE",
                        "url": "https://cursor.com/agents/bc-busy",
                        "updatedAt": "2026-10-06T10:00:00.000Z",
                    },
                    {
                        "id": "bc-done",
                        "name": "Закончил",
                        "status": "IDLE",
                        "url": "javascript:alert(1)",
                        "updatedAt": "2026-10-06T09:00:00.000Z",
                    },
                ],
                "nextCursor": "page-2",
            }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class OfficeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        FakeCursor.seen_auth = []
        FakeCursor.mode = "ok"
        cls.cursor = ThreadingHTTPServer(("127.0.0.1", 0), FakeCursor)
        cls.cursor_port = cls.cursor.server_address[1]
        threading.Thread(target=cls.cursor.serve_forever, daemon=True).start()
        cls.key_path = Path(os.environ.get("TMPDIR", "/tmp")) / "cursor-office-test-key"
        if cls.key_path.exists():
            cls.key_path.unlink()
        os.environ["OFFICE_API_BASE"] = f"http://127.0.0.1:{cls.cursor_port}"
        os.environ["OFFICE_KEY_PATH"] = str(cls.key_path)
        os.environ["OFFICE_NO_BROWSER"] = "1"
        server.API_ROOT = os.environ["OFFICE_API_BASE"]
        server.KEY_PATH = cls.key_path
        cls.office = ThreadingHTTPServer(("127.0.0.1", 0), server.OfficeHandler)
        cls.office_port = cls.office.server_address[1]
        threading.Thread(target=cls.office.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.office.shutdown()
        cls.cursor.shutdown()
        cls.key_path.unlink(missing_ok=True)

    def setUp(self) -> None:
        server.delete_key()
        FakeCursor.mode = "ok"
        FakeCursor.seen_auth = []

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.office_port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        if path.startswith("/api/") or path.endswith(".json"):
            return status, json.loads(raw.decode())
        return status, raw.decode()

    def test_demo_poses(self) -> None:
        status, payload = self.request("GET", "/api/demo")
        self.assertEqual(status, 200)
        poses = [item["pose"] for item in payload["agents"]]
        self.assertEqual(poses, ["working", "working", "resting", "away"])

    def test_key_roundtrip_hides_secret_and_paginates(self) -> None:
        status, saved = self.request("POST", "/api/key", {"apiKey": "secret-key"})
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.key_path.read_text(encoding="utf-8").strip(), "secret-key")
        self.assertEqual(self.key_path.stat().st_mode & 0o777, 0o600)
        status, office = self.request("GET", "/api/office")
        self.assertEqual(status, 200)
        self.assertNotIn("secret-key", json.dumps(office))
        self.assertEqual([item["pose"] for item in office["agents"]], ["working", "resting", "away"])
        self.assertTrue(all(header == "Bearer secret-key" for header in FakeCursor.seen_auth))
        names = [item["name"] for item in office["agents"]]
        self.assertIn("<img src=x onerror=alert(1)>", names)

    def test_bad_key_is_rejected(self) -> None:
        FakeCursor.mode = "deny"
        status, payload = self.request("POST", "/api/key", {"apiKey": "nope"})
        self.assertEqual(status, 401)
        self.assertIn("не подошёл", payload["error"])
        self.assertFalse(self.key_path.exists())

    def test_page_has_office(self) -> None:
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Офис", html)
        self.assertIn("/office.js", html)


if __name__ == "__main__":
    unittest.main()
