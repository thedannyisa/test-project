#!/usr/bin/env python3
"""Local window that shows Cursor cloud agents as office workers.

The API key stays on this computer. The server listens only on 127.0.0.1.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
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


TRUNCATED_KEY = (
    "Это короткий кусок из таблицы, не весь ключ. "
    "Нажми Add, создай ключ и скопируй длинную строку, которую Cursor покажет один раз."
)


def clean_key(value: str) -> str:
    key = value.strip().strip("\"'")
    key = "".join(key.split())
    return key


def key_problem(key: str) -> str | None:
    if not key:
        return "Вставь ключ целиком, одной строкой"
    if "..." in key or "…" in key or len(key) < 25:
        return TRUNCATED_KEY
    return None


def authorization_value(api_key: str, scheme: str) -> str:
    if scheme == "basic":
        token = base64.b64encode(f"{api_key}:".encode()).decode("ascii")
        return f"Basic {token}"
    return f"Bearer {api_key}"


def cursor_get(api_key: str, path: str) -> dict:
    refused: CursorApiError | None = None
    for scheme in ("basic", "bearer"):
        request = urllib.request.Request(
            API_ROOT + path,
            headers={
                "Authorization": authorization_value(api_key, scheme),
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
            error = CursorApiError(exc.code, message)
            if exc.code in {401, 403}:
                refused = error
                continue
            raise error from exc
        except urllib.error.URLError as exc:
            raise CursorApiError(0, "Не получилось достучаться до Cursor") from exc
        if not isinstance(payload, dict):
            raise CursorApiError(502, "Cursor ответил непонятно")
        return payload
    assert refused is not None
    raise refused


def fetch_agents(api_key: str, limit: int = 100, pages: int = MAX_PAGES) -> list[dict]:
    items: list[dict] = []
    cursor = None
    for _ in range(pages):
        query = {"limit": str(limit), "includeArchived": "true"}
        if cursor:
            query["cursor"] = cursor
        payload = cursor_get(api_key, "/v1/agents?" + urllib.parse.urlencode(query))
        batch = payload.get("items") or []
        if isinstance(batch, list):
            items.extend(item for item in batch if isinstance(item, dict))
        cursor = payload.get("nextCursor")
        if not cursor:
            break
    agents = [public_agent(item) for item in items]
    agents.sort(key=lambda agent: ({"working": 0, "resting": 1, "away": 2}[agent["pose"]], agent["name"]))
    return agents


def check_key(api_key: str) -> None:
    cursor_get(api_key, "/v1/me")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_USAGE_OPENER = urllib.request.build_opener(_NoRedirect)


def _blank_meter() -> dict:
    return {
        "available": False,
        "usedPercent": None,
        "remainingPercent": None,
        "level": "unknown",
        "reason": "Недоступно",
    }


def _blank_reset() -> dict:
    return {"available": False, "days": None, "at": None, "reason": "Недоступно"}


def _blank_limits(configured: bool) -> dict:
    reason = "Сохрани ключ, чтобы увидеть зарплату" if not configured else "Недоступно"
    meter = _blank_meter()
    meter["reason"] = reason
    reset = _blank_reset()
    reset["reason"] = reason
    return {
        "configured": configured,
        "cursorModels": dict(meter),
        "otherModels": dict(meter),
        "grokBot": dict(meter),
        "reset": reset,
        "grokReset": dict(reset),
    }


def _percent(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or number < 0 or number > 100:
        return None
    return round(number, 1)


def _meter(used: float | None) -> dict:
    if used is None:
        return _blank_meter()
    remaining = round(100 - used, 1)
    if used >= 100:
        level = "empty"
    elif used >= 90:
        level = "hot"
    elif used >= 70:
        level = "warn"
    else:
        level = "ok"
    return {
        "available": True,
        "usedPercent": used,
        "remainingPercent": remaining,
        "level": level,
        "reason": None,
    }


def _percent_in_text(text) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    return _percent(match.group(1))


def _reset_from_timestamp(value) -> dict:
    if value is None or value == "":
        return _blank_reset()
    moment = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds = seconds / 1000
        moment = datetime.fromtimestamp(seconds, timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return _reset_from_timestamp(int(text))
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return _blank_reset()
    if moment is None:
        return _blank_reset()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds_left = (moment - datetime.now(timezone.utc)).total_seconds()
    days = math.ceil(seconds_left / 86400) if seconds_left > 0 else 0
    return {"available": True, "days": days, "at": moment.isoformat(), "reason": None}


def parse_usage_summary(payload: dict | None) -> tuple[dict, dict, dict]:
    cursor_meter = _blank_meter()
    other_meter = _blank_meter()
    reset = _blank_reset()
    if not isinstance(payload, dict):
        return cursor_meter, other_meter, reset
    plan = {}
    individual = payload.get("individualUsage")
    if isinstance(individual, dict) and isinstance(individual.get("plan"), dict):
        plan = individual["plan"]
    cursor_used = _percent(plan.get("autoPercentUsed"))
    other_used = _percent(plan.get("apiPercentUsed"))
    if cursor_used is None:
        cursor_used = _percent_in_text(payload.get("autoModelSelectedDisplayMessage"))
    if other_used is None:
        other_used = _percent_in_text(payload.get("namedModelSelectedDisplayMessage"))
    if cursor_used is not None:
        cursor_meter = _meter(cursor_used)
    if other_used is not None:
        other_meter = _meter(other_used)
    reset = _reset_from_timestamp(payload.get("billingCycleEnd"))
    return cursor_meter, other_meter, reset


def parse_grok_status(payload: dict | None) -> tuple[dict, dict]:
    meter = _blank_meter()
    reset = _blank_reset()
    if not isinstance(payload, dict):
        return meter, reset
    if payload.get("includedLimitZero") is True or payload.get("hasNonZeroIncludedLimit") is False:
        meter["reason"] = "Нет недельного лимита"
        return meter, reset
    used = _percent(payload.get("usagePercent"))
    if used is None and isinstance(payload.get("usage"), dict):
        used = _percent(payload["usage"].get("usagePercent"))
    if used is not None:
        meter = _meter(used)
    reset = _reset_from_timestamp(
        payload.get("nextResetTimestampUtc")
        or payload.get("nextResetAt")
        or payload.get("resetAt")
    )
    return meter, reset


def _read_authorized_json(api_key: str, url: str, method: str = "GET", body: dict | None = None) -> dict | None:
    raw = None if body is None else json.dumps(body).encode("utf-8")
    for scheme in ("bearer", "basic"):
        request = urllib.request.Request(
            url,
            data=raw,
            method=method,
            headers={
                "Authorization": authorization_value(api_key, scheme),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with _USAGE_OPENER.open(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def fetch_limits(api_key: str) -> dict:
    limits = _blank_limits(True)
    summary_urls = [
        os.environ.get("OFFICE_USAGE_SUMMARY_URL", "https://cursor.com/api/usage-summary"),
        API_ROOT + "/v1/usage-summary",
    ]
    for url in summary_urls:
        cursor_meter, other_meter, reset = parse_usage_summary(_read_authorized_json(api_key, url))
        if cursor_meter["available"] or other_meter["available"] or reset["available"]:
            limits["cursorModels"] = cursor_meter
            limits["otherModels"] = other_meter
            limits["reset"] = reset
            break
    grok_url = os.environ.get(
        "OFFICE_GROK_USAGE_URL",
        "https://cursor.com/api/dashboard/get-sand-usage-status",
    )
    grok_meter, grok_reset = parse_grok_status(
        _read_authorized_json(api_key, grok_url, method="POST", body={})
    )
    limits["grokBot"] = grok_meter
    limits["grokReset"] = grok_reset
    return limits


def limits_payload() -> dict:
    key = read_key()
    if not key:
        return _blank_limits(False)
    return fetch_limits(key)


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
        if path == "/api/limits":
            self._send_json(limits_payload())
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
        key = clean_key(str(payload.get("apiKey") or ""))
        problem = key_problem(key)
        if problem:
            self._send_json({"ok": False, "error": problem}, status=400)
            return
        try:
            check_key(key)
        except CursorApiError as exc:
            status = 401 if exc.status in {401, 403} else 502
            message = (
                "Cursor не принял этот ключ. Нажми Add и скопируй новый ключ сразу, целиком."
                if exc.status in {401, 403}
                else exc.message
            )
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
