#!/usr/bin/env python3
"""Small touchscreen panel for Schedule/Away control of a Eufy HomeBase."""

from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import parse


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.getenv("PANEL_DATA_DIR", "/var/lib/eufy-panel"))
HOST = os.getenv("PANEL_HOST", "127.0.0.1")
PORT = int(os.getenv("PANEL_PORT", "8765"))
PANEL_NAME = os.getenv("PANEL_NAME", "Home security")
PROVIDER_NAME = os.getenv("PANEL_PROVIDER", "demo").strip().lower()

ALLOWED_MODES = {"schedule", "away"}
ACTIVE_MODE_LABELS = {
    0: "Away",
    1: "Home",
    3: "Custom 1",
    4: "Custom 2",
    5: "Custom 3",
    63: "Disarmed",
}
SESSION_COOKIE = "eufy_panel_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

logging.basicConfig(
    level=os.getenv("PANEL_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("eufy-panel")


def homepage_status(state: dict) -> tuple[str, str]:
    """Return a compact tile status and the active schedule rule."""
    mode = state.get("mode", "unknown")
    try:
        current_mode = int(state.get("current_mode", -1))
    except (TypeError, ValueError):
        current_mode = -1
    active_mode = ACTIVE_MODE_LABELS.get(current_mode, "Unknown")
    if mode == "schedule":
        return f"Schedule · {active_mode}", active_mode
    if mode == "away":
        return "Armed", "Away"
    return "Unavailable", active_mode


class ProviderError(RuntimeError):
    """A safe-to-display provider error."""


class DemoProvider:
    live = False
    label = "Demo"

    def __init__(self) -> None:
        self._path = DATA_DIR / "state.json"
        self._lock = threading.Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"mode": "schedule", "updated_at": int(time.time())})

    def _read(self) -> dict:
        try:
            state = json.loads(self._path.read_text(encoding="utf-8"))
            if state.get("mode") not in ALLOWED_MODES:
                raise ValueError("invalid mode")
            return state
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOG.warning("Resetting invalid demo state: %s", exc)
            state = {"mode": "schedule", "updated_at": int(time.time())}
            self._write(state)
            return state

    def _write(self, state: dict) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(self._path)

    def status(self) -> dict:
        with self._lock:
            state = self._read()
        return {**state, "connected": True}

    def set_mode(self, mode: str) -> dict:
        state = {"mode": mode, "updated_at": int(time.time())}
        with self._lock:
            self._write(state)
        return {**state, "connected": True}


class EufyWsProvider:
    """Direct bridge to bropat/eufy-security-ws using its schema-12 API."""

    live = True
    label = "Eufy HomeBase"

    MODE_TO_VALUE = {"away": 0, "schedule": 2}
    VALUE_TO_MODE = {value: key for key, value in MODE_TO_VALUE.items()}

    def __init__(self) -> None:
        self.url = os.getenv("EUFY_WS_URL", "ws://127.0.0.1:3001")
        self.station_serial = os.getenv("EUFY_STATION_SERIAL", "").strip()
        try:
            from websockets.sync.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "The eufy_ws provider requires the Python websockets package"
            ) from exc
        self._connect = connect

    @staticmethod
    def _receive(socket, timeout: float = 5.0) -> dict:
        message = socket.recv(timeout=timeout)
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    @staticmethod
    def _check_event(message: dict) -> None:
        if message.get("type") != "event":
            return
        event = message.get("event", {})
        if event.get("source") == "driver" and event.get("event") == "verify code":
            raise ProviderError(
                "Eufy needs a verification code; run sudo eufy-panel-verify on the Pi"
            )
        if event.get("source") == "driver" and event.get("event") == "captcha request":
            raise ProviderError("Eufy requested a CAPTCHA during sign-in")

    def _wait_result(self, socket, message_id: str, timeout: float = 8.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._receive(socket, max(0.1, deadline - time.monotonic()))
            self._check_event(message)
            if message.get("type") != "result" or message.get("messageId") != message_id:
                continue
            if not message.get("success"):
                code = message.get("errorCode", "unknown_error")
                raise ProviderError(f"Eufy bridge rejected the command ({code})")
            return message.get("result", {})
        raise ProviderError("Eufy bridge did not respond")

    def _send_command(self, socket, command: dict, timeout: float = 8.0) -> dict:
        socket.send(json.dumps(command))
        return self._wait_result(socket, str(command["messageId"]), timeout)

    def _start_session(self):
        socket = None
        try:
            socket = self._connect(self.url, open_timeout=4, close_timeout=1)
            version = self._receive(socket, 4)
            if version.get("type") != "version":
                raise ProviderError("Eufy bridge returned an unexpected greeting")
            max_schema = int(version.get("maxSchemaVersion", 0))
            if max_schema < 3:
                raise ProviderError("Eufy bridge API is too old")
            schema = min(12, max_schema)
            self._send_command(
                socket,
                {
                    "messageId": "panel-schema",
                    "command": "set_api_schema",
                    "schemaVersion": schema,
                },
            )
            listening = self._send_command(
                socket,
                {"messageId": "panel-listen", "command": "start_listening"},
            )
            return socket, listening.get("state", {})
        except ProviderError:
            if socket is not None:
                socket.close()
            raise
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if socket is not None:
                socket.close()
            LOG.error("Eufy bridge connection failed: %s", exc)
            raise ProviderError("Eufy bridge is unavailable") from exc

    def _select_station(self, state: dict) -> dict:
        stations = [item for item in state.get("stations", []) if isinstance(item, dict)]
        if not stations:
            if not state.get("driver", {}).get("connected", False):
                raise ProviderError("Eufy bridge is waiting for cloud sign-in")
            raise ProviderError("No Eufy HomeBase was found")

        if self.station_serial:
            for station in stations:
                if station.get("serialNumber") == self.station_serial:
                    return station
            raise ProviderError("The configured Eufy HomeBase was not found")

        s380 = [
            station
            for station in stations
            if str(station.get("serialNumber", "")).upper().startswith("T8030")
            or "S380" in str(station.get("model", "")).upper()
        ]
        if len(s380) == 1:
            return s380[0]
        if len(stations) == 1:
            return stations[0]
        raise ProviderError("More than one HomeBase was found; configure its serial number")

    def _station_state(self, station: dict) -> dict:
        try:
            current = int(station.get("currentMode", -1))
            guard = int(station.get("guardMode", -1))
        except (TypeError, ValueError):
            current, guard = -1, -1
        # Schedule remains the selected guard mode while currentMode reflects
        # whichever scheduled rule (for example Home or Away) is active now.
        if guard == 2:
            pending = False
            displayed = guard
        else:
            pending = guard in self.VALUE_TO_MODE and current != guard
            displayed = guard if pending else current
        return {
            "mode": self.VALUE_TO_MODE.get(displayed, "unknown"),
            "pending": pending,
            "current_mode": current,
            "guard_mode": guard,
            "station_serial": station.get("serialNumber", ""),
            "updated_at": int(time.time()),
            "connected": bool(station.get("connected", True)),
        }

    def status(self) -> dict:
        socket = None
        try:
            socket, state = self._start_session()
            return self._station_state(self._select_station(state))
        finally:
            if socket is not None:
                socket.close()

    def set_mode(self, mode: str) -> dict:
        socket = None
        try:
            socket, state = self._start_session()
            station = self._select_station(state)
            serial = str(station["serialNumber"])
            requested = self.MODE_TO_VALUE[mode]
            self._send_command(
                socket,
                {
                    "messageId": "panel-set-mode",
                    "command": "station.set_guard_mode",
                    "serialNumber": serial,
                    "mode": requested,
                },
                timeout=12,
            )

            # Read back HomeBase properties; this distinguishes a confirmed mode
            # from an accepted command that is still inside its leaving delay.
            for attempt in range(3):
                if attempt:
                    time.sleep(0.8)
                result = self._send_command(
                    socket,
                    {
                        "messageId": f"panel-read-mode-{attempt}",
                        "command": "station.get_properties",
                        "serialNumber": serial,
                    },
                )
                properties = result.get("properties", {})
                observed = self._station_state(
                    {
                        **properties,
                        "serialNumber": serial,
                        "connected": True,
                    }
                )
                if observed["mode"] == mode:
                    return observed
            raise ProviderError("HomeBase did not confirm the requested mode")
        except ProviderError:
            raise
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            LOG.error("Eufy mode command failed: %s", exc)
            raise ProviderError("Eufy bridge is unavailable") from exc
        finally:
            if socket is not None:
                socket.close()


def make_provider():
    if PROVIDER_NAME == "demo":
        return DemoProvider()
    if PROVIDER_NAME in {"eufy_ws", "eufy-ws", "eufy"}:
        return EufyWsProvider()
    raise RuntimeError(f"Unsupported PANEL_PROVIDER: {PROVIDER_NAME}")


PROVIDER = make_provider()
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()


def prune_sessions(now: float) -> None:
    stale = [sid for sid, value in SESSIONS.items() if now - value["seen"] > SESSION_TTL_SECONDS]
    for sid in stale:
        SESSIONS.pop(sid, None)


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "EufyPanel/0.1"

    def log_message(self, fmt: str, *args) -> None:
        LOG.info("%s %s", self.address_string(), fmt % args)

    def _headers(self, status: int, content_type: str, length: int, cookie: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _json(self, status: int, payload: dict, cookie: str | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), cookie)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str, **extra) -> None:
        self._json(status, {"ok": False, "error": message, **extra})

    def _session(self) -> tuple[str, dict, str | None]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        sid = cookie.get(SESSION_COOKIE).value if cookie.get(SESSION_COOKIE) else ""
        now = time.time()
        set_cookie = None
        with SESSIONS_LOCK:
            prune_sessions(now)
            session = SESSIONS.get(sid)
            if session is None:
                sid = secrets.token_urlsafe(32)
                session = {
                    "csrf": secrets.token_urlsafe(32),
                    "seen": now,
                }
                SESSIONS[sid] = session
                set_cookie = (
                    f"{SESSION_COOKIE}={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}"
                )
            else:
                session["seen"] = now
        return sid, session, set_cookie

    def _status_payload(self, session: dict) -> dict:
        state = PROVIDER.status()
        return {
            "ok": True,
            "panel_name": PANEL_NAME,
            "provider": PROVIDER.label,
            "live": PROVIDER.live,
            "csrf": session["csrf"],
            **state,
        }

    def _homepage_payload(self) -> dict:
        state = PROVIDER.status()
        mode = state.get("mode", "unknown")
        status, active_mode = homepage_status(state)
        return {
            "ok": mode in ALLOWED_MODES,
            "mode": mode if mode in ALLOWED_MODES else "unknown",
            "status": status,
            "active_mode": active_mode,
            "connected": bool(state.get("connected", False)),
            "provider": PROVIDER.label,
        }

    def _serve_static(self, relative_path: str) -> None:
        clean = relative_path.strip("/") or "index.html"
        if clean not in {"index.html", "app.css", "app.js", "favicon.svg"}:
            self._error(HTTPStatus.NOT_FOUND, "Not found")
            return
        path = STATIC_DIR / clean
        try:
            body = path.read_bytes()
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        self._headers(HTTPStatus.OK, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = parse.urlparse(self.path).path
        if path == "/api/health":
            self._json(
                HTTPStatus.OK,
                {"ok": True, "provider": PROVIDER.label, "live": PROVIDER.live},
            )
            return
        if path == "/api/homepage":
            try:
                self._json(HTTPStatus.OK, self._homepage_payload())
            except ProviderError:
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": False,
                        "mode": "unknown",
                        "status": "Unavailable",
                        "active_mode": "Unknown",
                        "connected": False,
                        "provider": PROVIDER.label,
                    },
                )
            return
        if path == "/api/status":
            _, session, set_cookie = self._session()
            try:
                self._json(HTTPStatus.OK, self._status_payload(session), set_cookie)
            except ProviderError as exc:
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "ok": False,
                        "error": str(exc),
                        "panel_name": PANEL_NAME,
                        "provider": PROVIDER.label,
                        "live": PROVIDER.live,
                        "csrf": session["csrf"],
                    },
                    set_cookie,
                )
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = parse.urlparse(self.path).path
        if path != "/api/mode":
            self._error(HTTPStatus.NOT_FOUND, "Not found")
            return

        _, session, set_cookie = self._session()
        if not hmac.compare_digest(
            self.headers.get("X-CSRF-Token", ""), session["csrf"]
        ):
            self._json(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "Security token expired; refresh the panel"},
                set_cookie,
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 1024:
                raise ValueError("invalid length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            mode = payload.get("mode", "")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            self._error(HTTPStatus.BAD_REQUEST, "Invalid request")
            return

        if mode not in ALLOWED_MODES:
            self._error(HTTPStatus.BAD_REQUEST, "Unknown security mode")
            return

        try:
            state = PROVIDER.set_mode(mode)
        except ProviderError as exc:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "provider": PROVIDER.label,
                "live": PROVIDER.live,
                **state,
            },
        )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PanelHandler)
    LOG.info("Starting %s provider on http://%s:%s", PROVIDER.label, HOST, PORT)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
