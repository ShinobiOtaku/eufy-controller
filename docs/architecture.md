# Architecture

## Components

The controller has three runtime components:

1. A static touch-oriented browser interface.
2. A small Python HTTP service that validates requests and translates modes.
3. The community `eufy-security-ws` Docker container, which owns the Eufy
   session and talks to the cloud and HomeBase.

nginx is the public entry point. The Python service listens on
`127.0.0.1:8765`; the Docker WebSocket port is published only on
`127.0.0.1:3001`. Neither backend port should be reachable directly from the
LAN.

## Mode mapping

| Panel mode | Eufy guard mode |
|---|---:|
| Away | `0` |
| Schedule | `2` |

Eufy exposes both `guardMode` and `currentMode`. When Schedule is selected,
`guardMode` remains `2`, while `currentMode` can reflect the Home or Away rule
currently selected by the timetable. The panel therefore uses `guardMode` to
display Schedule and does not mistake the active rule for a manual mode.

No mapping exists for Home or Disarmed. Requests for them fail validation
before reaching the bridge.

## Request flow

1. `GET /api/status` establishes a short-lived browser session and returns a
   CSRF token.
2. `GET /api/homepage` returns only mode, display status, connection, and
   provider fields for Homepage's server-side widget polling; it does not
   create a browser session.
   When Schedule is selected, its compact `status` combines the guard mode and
   active rule, such as `Schedule · Home`.
3. `POST /api/mode` requires the browser token and accepts only `schedule` or
   `away`.
4. The backend opens a localhost WebSocket connection using API schema 12.
5. It sends `station.set_guard_mode` to the selected HomeBase.
6. It reads station properties back and reports the observed state.

## HomeBase selection

An explicit `EUFY_STATION_SERIAL` wins. Otherwise the backend selects a single
station whose model or serial identifies an S380/T8030. If the account exposes
only one station, that station is selected. Ambiguous accounts fail safely and
require an explicit serial.

## Persistent data

| Path | Owner | Purpose |
|---|---|---|
| `/etc/eufy-panel.env` | root | Panel configuration |
| `/etc/eufy-security-ws.env` | root | Non-secret bridge options |
| `/etc/eufy-security-ws/` | root | Eufy username/password secret files |
| `/var/lib/eufy-panel/` | `eufypanel` | Demo state |
| `/var/lib/eufy-security-ws/` | root/container | Persisted Eufy session and bridge state |

The browser never receives the Eufy username, password, authentication token,
or HomeBase serial.
