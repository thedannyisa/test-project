#!/usr/bin/env python3
"""Tests for the local Cursor office server."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
import unittest
import urllib.error
import urllib.parse
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
        auth = self.headers.get("Authorization") or ""
        self.seen_auth.append(auth)
        if self.mode == "bearer-only" and not auth.startswith("Bearer "):
            body = json.dumps({"message": "use bearer"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if urllib.parse.urlsplit(self.path).path == "/v1/me":
            if self.mode == "deny":
                body = json.dumps({"message": "bad key"}).encode()
                self.send_response(401)
            else:
                body = json.dumps({"apiKeyName": "test"}).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
        os.environ["OFFICE_CATS_PATH"] = str(cls.key_path.with_name("cursor-office-test-cats.json"))
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
        Path(os.environ["OFFICE_CATS_PATH"]).unlink(missing_ok=True)

    def setUp(self) -> None:
        server.delete_key()
        Path(os.environ["OFFICE_CATS_PATH"]).unlink(missing_ok=True)
        os.environ.pop("OFFICE_CURSOR_STATE_DB", None)
        os.environ["OFFICE_STRIPE_URL"] = ""
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
        self.assertEqual(
            [(item["catName"], item["role"]) for item in payload["agents"]],
            [
                ("Барсик", "Тестировщик"),
                ("Мурзик", "Дизайнер кнопок"),
                ("Рыжик", "Документация"),
                ("Снежок", "Архивная задача"),
            ],
        )
        self.assertFalse(Path(os.environ["OFFICE_CATS_PATH"]).exists())

    def test_key_roundtrip_hides_secret_and_paginates(self) -> None:
        full_key = "crsr_" + ("a" * 40)
        status, saved = self.request("POST", "/api/key", {"apiKey": f"  {full_key}  "})
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.key_path.read_text(encoding="utf-8").strip(), full_key)
        self.assertEqual(self.key_path.stat().st_mode & 0o777, 0o600)
        status, office = self.request("GET", "/api/office")
        self.assertEqual(status, 200)
        self.assertNotIn(full_key, json.dumps(office))
        self.assertEqual([item["pose"] for item in office["agents"]], ["working", "resting", "away"])
        expected = "Basic " + base64.b64encode(b"crsr_" + b"a" * 40 + b":").decode()
        self.assertTrue(all(header == expected for header in FakeCursor.seen_auth))
        names = [item["name"] for item in office["agents"]]
        self.assertIn("<img src=x onerror=alert(1)>", names)

    def test_bad_key_is_rejected(self) -> None:
        FakeCursor.mode = "deny"
        status, payload = self.request("POST", "/api/key", {"apiKey": "crsr_" + ("b" * 40)})
        self.assertEqual(status, 401)
        self.assertIn("не принял", payload["error"])
        self.assertFalse(self.key_path.exists())

    def test_table_snippet_is_rejected_before_cursor(self) -> None:
        status, payload = self.request("POST", "/api/key", {"apiKey": "crsr_...86c2"})
        self.assertEqual(status, 400)
        self.assertIn("Add", payload["error"])
        self.assertEqual(FakeCursor.seen_auth, [])

    def test_bearer_is_used_when_basic_is_refused(self) -> None:
        FakeCursor.mode = "bearer-only"
        full_key = "crsr_" + ("c" * 40)
        status, saved = self.request("POST", "/api/key", {"apiKey": full_key})
        self.assertEqual(status, 200, saved)
        self.assertTrue(any(header.startswith("Bearer ") for header in FakeCursor.seen_auth))

    def test_page_has_office(self) -> None:
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Офис", html)
        self.assertIn("ЛИМИТЫ", html)
        self.assertIn("/office.js", html)
        self.assertIn("Настройки", html)
        self.assertIn('id="settings"', html)
        self.assertLess(html.find('id="settings"'), html.find('id="key-form"'))
        self.assertNotIn("Ключ Cursor", html.split('id="settings"', 1)[0])

    def test_job_titles_are_russian(self) -> None:
        self.assertEqual(server.role_title("Office presence"), "Дежурство в офисе")
        self.assertEqual(server.role_title("Set up test-project environment"), "Настройка среды test-project")
        self.assertEqual(server.role_title("Application development"), "Разработка приложения")
        self.assertEqual(server.role_title("Application development (fork)"), "Разработка приложения (копия)")
        self.assertEqual(server.role_title("  пишет   тесты "), "Тестировщик")

    def test_cat_names_stick_when_status_changes(self) -> None:
        original = [
            {"id": "presence", "name": "Office presence"},
            {"id": "setup", "name": "Set up test-project environment"},
            {"id": "app", "name": "Application development"},
            {"id": "fork", "name": "Application development (fork)"},
        ]
        server.assign_cats([dict(item) for item in original])
        moved = server.assign_cats([
            {"id": "setup", "name": "Set up test-project environment"},
            {"id": "presence", "name": "Office presence"},
            {"id": "fork", "name": "Application development (fork)"},
            {"id": "app", "name": "Application development"},
        ])
        by_id = {item["id"]: item for item in moved}
        self.assertEqual(by_id["presence"]["catName"], "Барсик")
        self.assertEqual(by_id["setup"]["catName"], "Мурзик")
        self.assertEqual(by_id["presence"]["role"], "Дежурство в офисе")
        self.assertEqual(by_id["setup"]["role"], "Настройка среды test-project")
        self.assertEqual(by_id["app"]["role"], "Разработка приложения")
        self.assertEqual(by_id["fork"]["role"], "Разработка приложения (копия)")
        saved = Path(os.environ["OFFICE_CATS_PATH"]).read_text(encoding="utf-8")
        self.assertNotIn("crsr_", saved)

    def test_limits_without_key_are_unavailable(self) -> None:
        status, payload = self.request("GET", "/api/limits")
        self.assertEqual(status, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["cursorModels"]["available"])
        self.assertIsNone(payload["cursorModels"]["usedPercent"])
        self.assertNotIn("crsr_", json.dumps(payload))

    def test_limits_parse_real_fields_and_skip_missing_ones(self) -> None:
        cursor_meter, other_meter, reset = server.parse_usage_summary({
            "billingCycleEnd": "2099-01-15T00:00:00.000Z",
            "individualUsage": {"plan": {"autoPercentUsed": 42.5, "apiPercentUsed": 7}},
        })
        self.assertEqual(cursor_meter["usedPercent"], 42.5)
        self.assertEqual(cursor_meter["remainingPercent"], 57.5)
        self.assertEqual(other_meter["usedPercent"], 7.0)
        self.assertTrue(reset["available"])
        self.assertGreater(reset["days"], 0)
        empty_cursor, empty_other, empty_reset = server.parse_usage_summary({})
        self.assertFalse(empty_cursor["available"])
        self.assertFalse(empty_other["available"])
        self.assertFalse(empty_reset["available"])
        grok, grok_reset = server.parse_grok_status({
            "usagePercent": 91,
            "hasNonZeroIncludedLimit": True,
            "nextResetTimestampUtc": "2099-01-08T00:00:00.000Z",
        })
        self.assertEqual(grok["level"], "hot")
        self.assertTrue(grok_reset["available"])
        missing, _reset = server.parse_grok_status({"includedLimitZero": True})
        self.assertFalse(missing["available"])
        self.assertEqual(missing["reason"], "Нет недельного лимита")

    def test_subscription_end_is_not_the_limit_reset(self) -> None:
        ending = server.parse_subscription({
            "membershipType": "pro",
            "subscriptionStatus": "active",
            "pendingCancellationDate": "2099-01-15T00:00:00.000Z",
            "daysRemainingOnTrial": 0,
            "billingCycleEnd": "2099-02-01T00:00:00.000Z",
        })
        self.assertTrue(ending["available"])
        self.assertFalse(ending["renews"])
        self.assertEqual(ending["plan"], "Pro")
        self.assertGreater(ending["days"], 0)
        self.assertTrue(str(ending["at"]).startswith("2099-01-15"))
        renewing = server.parse_subscription({
            "membershipType": "ultra",
            "subscriptionStatus": "active",
            "pendingCancellationDate": "",
            "daysRemainingOnTrial": 0,
        })
        self.assertTrue(renewing["renews"])
        self.assertEqual(renewing["plan"], "Ultra")
        self.assertIsNone(renewing["at"])
        self.assertIsNone(renewing["days"])
        trial = server.parse_subscription({
            "subscriptionStatus": "trialing",
            "daysRemainingOnTrial": 4,
            "pendingCancellationDate": "",
        })
        self.assertEqual(trial["days"], 4)
        self.assertIsNone(trial["at"])
        self.assertFalse(trial["renews"])
        self.assertFalse(server.parse_subscription(None)["available"])

    def test_limits_endpoint_uses_usage_api_without_leaking_key(self) -> None:
        class Usage(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def _send(self, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                self._send({
                    "billingCycleEnd": "2099-06-01T12:00:00.000Z",
                    "individualUsage": {"plan": {"autoPercentUsed": 42.5, "apiPercentUsed": 7}},
                })

            def do_POST(self) -> None:  # noqa: N802
                self._send({
                    "usagePercent": 91,
                    "hasNonZeroIncludedLimit": True,
                    "nextResetTimestampUtc": "2099-05-20T00:00:00.000Z",
                })

        usage = ThreadingHTTPServer(("127.0.0.1", 0), Usage)
        threading.Thread(target=usage.serve_forever, daemon=True).start()
        port = usage.server_address[1]
        os.environ["OFFICE_USAGE_SUMMARY_URL"] = f"http://127.0.0.1:{port}/api/usage-summary"
        os.environ["OFFICE_GROK_USAGE_URL"] = f"http://127.0.0.1:{port}/grok"
        full_key = "crsr_" + ("d" * 40)
        try:
            status, saved = self.request("POST", "/api/key", {"apiKey": full_key})
            self.assertEqual(status, 200, saved)
            status, payload = self.request("GET", "/api/limits")
            self.assertEqual(status, 200)
            self.assertEqual(payload["cursorModels"]["usedPercent"], 42.5)
            self.assertEqual(payload["otherModels"]["remainingPercent"], 93.0)
            self.assertEqual(payload["grokBot"]["usedPercent"], 91.0)
            self.assertEqual(payload["grokBot"]["level"], "hot")
            self.assertNotIn(full_key, json.dumps(payload))
        finally:
            usage.shutdown()
            os.environ.pop("OFFICE_USAGE_SUMMARY_URL", None)
            os.environ.pop("OFFICE_GROK_USAGE_URL", None)
            server.delete_key()

    def test_limits_use_local_cursor_login_without_leaking_it(self) -> None:
        secret = "office-session-secret"
        payload = base64.urlsafe_b64encode(json.dumps({"sub": "user_office"}).encode()).decode().rstrip("=")
        token = f"aaa.{payload}.{secret}"
        database = self.key_path.with_name("cursor-office-state.vscdb")
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("cursorAuth/accessToken", token),
        )
        connection.commit()
        connection.close()

        class Usage(BaseHTTPRequestHandler):
            seen_cookie = ""
            seen_auth = ""

            def log_message(self, fmt: str, *args) -> None:
                return

            def _send(self, payload: dict, status: int = 200) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _guard(self) -> bool:
                Usage.seen_cookie = self.headers.get("Cookie") or ""
                Usage.seen_auth = self.headers.get("Authorization") or ""
                if "WorkosCursorSessionToken=" not in Usage.seen_cookie:
                    self._send({"error": "not_authenticated"}, 401)
                    return False
                return True

            def do_GET(self) -> None:  # noqa: N802
                if not self._guard():
                    return
                if urllib.parse.urlsplit(self.path).path.endswith("/stripe"):
                    self._send({
                        "membershipType": "pro",
                        "subscriptionStatus": "active",
                        "pendingCancellationDate": "",
                        "daysRemainingOnTrial": 0,
                    })
                    return
                self._send({
                    "billingCycleEnd": "2099-06-01T12:00:00.000Z",
                    "individualUsage": {"plan": {"autoPercentUsed": 11, "apiPercentUsed": 22}},
                })

            def do_POST(self) -> None:  # noqa: N802
                if not self._guard():
                    return
                self._send({
                    "usagePercent": 33,
                    "hasNonZeroIncludedLimit": True,
                    "nextResetTimestampUtc": "2099-05-20T00:00:00.000Z",
                })

        usage = ThreadingHTTPServer(("127.0.0.1", 0), Usage)
        threading.Thread(target=usage.serve_forever, daemon=True).start()
        port = usage.server_address[1]
        os.environ["OFFICE_CURSOR_STATE_DB"] = str(database)
        os.environ["OFFICE_USAGE_SUMMARY_URL"] = f"http://127.0.0.1:{port}/api/usage-summary"
        os.environ["OFFICE_GROK_USAGE_URL"] = f"http://127.0.0.1:{port}/grok"
        os.environ["OFFICE_STRIPE_URL"] = f"http://127.0.0.1:{port}/stripe"
        try:
            status, saved = self.request("POST", "/api/key", {"apiKey": "crsr_" + ("e" * 40)})
            self.assertEqual(status, 200, saved)
            status, payload = self.request("GET", "/api/limits")
            self.assertEqual(status, 200)
            self.assertEqual(payload["cursorModels"]["usedPercent"], 11.0)
            self.assertEqual(payload["otherModels"]["usedPercent"], 22.0)
            self.assertEqual(payload["grokBot"]["usedPercent"], 33.0)
            self.assertTrue(payload["subscription"]["renews"])
            self.assertEqual(payload["subscription"]["plan"], "Pro")
            self.assertIsNone(payload["subscription"]["at"])
            self.assertNotEqual(payload["subscription"]["at"], payload["reset"]["at"])
            encoded = json.dumps(payload)
            self.assertNotIn(secret, encoded)
            self.assertNotIn(token, encoded)
            self.assertIn("%3A%3A", Usage.seen_cookie)
            self.assertNotIn(secret, Usage.seen_auth)
        finally:
            usage.shutdown()
            database.unlink(missing_ok=True)
            os.environ.pop("OFFICE_CURSOR_STATE_DB", None)
            os.environ.pop("OFFICE_USAGE_SUMMARY_URL", None)
            os.environ.pop("OFFICE_GROK_USAGE_URL", None)
            os.environ["OFFICE_STRIPE_URL"] = ""
            server.delete_key()


if __name__ == "__main__":
    unittest.main()
