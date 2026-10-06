#!/usr/bin/env python3
"""Local window that shows Cursor cloud agents as office workers.

The API key stays on this computer. The server listens only on 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_ROOT = os.environ.get("OFFICE_API_BASE", "https://api.cursor.com").rstrip("/")
HOST = "127.0.0.1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
KEY_PATH = Path(
    os.environ.get(
        "OFFICE_KEY_PATH",
        str(Path.home() / ".config" / "cursor-office" / "api-key"),
    )
)
DEFAULT_PORT = int(os.environ.get("OFFICE_PORT", "8765"))
MAX_PAGES = 10

POSES = {
    "ACTIVE": "working",
    "IDLE": "resting",
    "ARCHIVED": "away",
}

DEMO_AGENTS = [
    {
        "id": "demo-writing-tests",
        "name": "Пишет тесты",
        "status": "ACTIVE",
        "url": "https://cursor.com/agents",
        "updatedAt": "2026-10-06T10:40:00.000Z",
    },
    {
        "id": "demo-drawing-button",
        "name": "Рисует кнопку",
        "status": "ACTIVE",
        "url": "https://cursor.com/agents",
        "updatedAt": "2026-10-06T10:41:00.000Z",
    },
    {
        "id": "demo-readme-done",
        "name": "Закончил README",
        "status": "IDLE",
        "url": "https://cursor.com/agents",
        "updatedAt": "2026-10-06T10:20:00.000Z",
    },
    {
        "id": "demo-old-draft",
        "name": "Старая задача",
        "status": "ARCHIVED",
        "url": "https://cursor.com/agents",
        "updatedAt": "2026-10-01T08:00:00.000Z",
    },
]

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/office.css": ("office.css", "text/css; charset=utf-8"),
    "/office.js": ("office.js", "text/javascript; charset=utf-8"),
}


class CursorApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def read_key() -> str:
    try:
        return KEY_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_key(key: str) -> None:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_text(key + "\n", encoding="utf-8")
    KEY_PATH.chmod(0o600)


def delete_key() -> None:
    KEY_PATH.unlink(missing_ok=True)


def public_agent(item: dict) -> dict:
    status = str(item.get("status") or "IDLE").upper()
    if status not in POSES:
        status = "IDLE"
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "Без имени"),
        "status": status,
        "pose": POSES[status],
        "url": str(item.get("url") or ""),
        "updatedAt": str(item.get("updatedAt") or ""),
    }


def fetch_agents(api_key: str, limit: int = 100, pages: int = MAX_PAGES) -> list[dict]:
    items: list[dict] = []
    cursor = None
    for _ in range(pages):
        query = {"limit": str(limit), "includeArchived": "true"}
        if cursor:
            query["cursor"] = cursor
        url = API_ROOT + "/v1/agents?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = f"Cursor ответил {exc.code}"
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {}
            detail = parsed.get("message") or parsed.get("error") or ""
            if isinstance(detail, dict):
                detail = detail.get("message") or ""
            if isinstance(detail, str) and detail.strip():
                message = f"{message}: {detail.strip()[:180]}"
            raise CursorApiError(exc.code, message) from exc
        except urllib.error.URLError as exc:
            raise CursorApiError(0, "Не получилось достучаться до Cursor") from exc
        batch = payload.get("items") or []
        if isinstance(batch, list):
            items.extend(item for item in batch if isinstance(item, dict))
        cursor = payload.get("nextCursor")
        if not cursor:
            break
    agents = [public_agent(item) for item in items]
    agents.sort(key=lambda agent: ({"working": 0, "resting": 1, "away": 2}[agent["pose"]], agent["name"]))
    return agents


def office_payload() -> dict:
    key = read_key()
    if not key:
        return {"configured": False, "agents": [], "error": None}
    try:
        agents = fetch_agents(key)
    except CursorApiError as exc:
        return {"configured": True, "agents": [], "error": exc.message}
    return {"configured": True, "agents": agents, "error": None}


class OfficeHandler(BaseHTTPRequestHandler):
    server_version = "CursorOffice/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if self.path.startswith("/api/key"):
            print(f"office {self.command} /api/key")
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if path == "/api/office":
            self._send_json(office_payload())
            return
        if path == "/api/demo":
            agents = [public_agent(item) for item in DEMO_AGENTS]
            self._send_json({"configured": False, "agents": agents, "error": None, "demo": True})
            return
        static = STATIC_FILES.get(path)
        if static is None:
            self._send_json({"error": "Нет такой страницы"}, status=404)
            return
        name, content_type = static
        body = (STATIC_DIR / name).read_bytes()
        self._send_bytes(body, content_type)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/shutdown":
            self._send_json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path != "/api/key":
            self._send_json({"error": "Нет такой страницы"}, status=404)
            return
        payload = self._read_json()
        key = str(payload.get("apiKey") or "").strip()
        if not key or any(char in key for char in "\r\n\x00"):
            self._send_json({"ok": False, "error": "Вставь ключ целиком, одной строкой"}, status=400)
            return
        try:
            fetch_agents(key, limit=1, pages=1)
        except CursorApiError as exc:
            status = 401 if exc.status in {401, 403} else 502
            message = "Ключ не подошёл" if exc.status in {401, 403} else exc.message
            self._send_json({"ok": False, "error": message}, status=status)
            return
        write_key(key)
        self._send_json({"ok": True})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path != "/api/key":
            self._send_json({"error": "Нет такой страницы"}, status=404)
            return
        delete_key()
        self._send_json({"ok": True})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length > 8192:
            return {}
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)


def port_is_ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return False
    return payload.get("ok") is True


def serve(port: int | None = None, open_browser: bool | None = None) -> None:
    chosen = DEFAULT_PORT if port is None else port
    if chosen != 0 and port_is_ours(chosen):
        url = f"http://{HOST}:{chosen}"
        print(f"Офис уже открыт: {url}")
        if open_browser is None:
            open_browser = os.environ.get("OFFICE_NO_BROWSER") != "1"
        if open_browser:
            webbrowser.open(url)
        return

    httpd = ThreadingHTTPServer((HOST, chosen), OfficeHandler)
    actual = httpd.server_address[1]
    url = f"http://{HOST}:{actual}"
    print(f"Офис слушает {url}")
    if open_browser is None:
        open_browser = os.environ.get("OFFICE_NO_BROWSER") != "1"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
