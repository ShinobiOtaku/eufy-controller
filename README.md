# Front-Door Dashboard

A small, locally hosted dashboard for the phone or touchscreen beside the front
door. It puts the time, today's weather, a six-hour rain heads-up, collection
night reminders, and Eufy **Schedule** / **Away** controls on one glanceable
screen. It can also be linked from a
[Homepage](https://gethomepage.dev/) dashboard.

The browser talks only to a local Python service. The Pi fetches and caches
weather from [Open-Meteo](https://open-meteo.com/) every 10 minutes. Eufy
credentials stay in root-owned files on the Pi and are consumed by the
community [`eufy-security-ws`](https://github.com/bropat/eufy-security-ws)
bridge.

> [!IMPORTANT]
> Eufy does not provide an official public local API for this workflow. This
> project depends on the unofficial `eufy-security-client` ecosystem and may
> need updates when Eufy changes its cloud or device protocols.

## What it does

- Portrait-first, kiosk-friendly clock and date
- Current temperature, conditions, feels-like temperature, wind, and high/low
- A prominent umbrella recommendation based on the next six hours
- Key-free Open-Meteo integration with a 10-minute server-side cache
- A Wednesday-afternoon-to-Thursday-morning bin card with local 3D artwork
- Alternating black and green/blue weeks, with the food caddy shown every week
- One-touch **Schedule** and **Away** controls
- Reads the HomeBase state back before reporting success
- Understands Schedule's active-rule behaviour (`guardMode=2`)
- Shows the active schedule rule on both the panel page and Homepage tile
- Automatically selects a single S380/T8030 HomeBase
- Supports an explicit HomeBase serial when an account has multiple stations
- Keeps the panel and bridge bound to localhost
- Provides a session-free read-only endpoint for a Homepage status widget
- Uses a CSRF token for mode-changing requests
- Starts in a non-operational demo mode until credentials are configured
- Does not require Home Assistant

There is intentionally no PIN. Anyone who can reach and operate the page can
switch between Schedule and Away. The backend rejects every other mode,
including Disarmed and Home.

## Architecture

```text
Kiosk browser / Homepage
        │ HTTP /eufy/
        ▼
nginx / Homepage host
        │ 127.0.0.1:8765
        ▼
Python panel service
        ├── HTTPS → Open-Meteo forecast API
        └── WebSocket 127.0.0.1:3001
                        ▼
              eufy-security-ws container
                        │ Eufy cloud / HomeBase P2P
                        ▼
              HomeBase (including S380 / T8030)
```

See [Architecture](docs/architecture.md) for the trust boundaries and mode
mapping.

## Requirements

- Raspberry Pi OS or another Debian-family distribution
- 64-bit or 32-bit ARM supported by the upstream Docker image
- `systemd` and outbound HTTPS for weather
- Docker
- Python 3 with `websockets`
- nginx or another reverse proxy
- A Eufy account with access to the HomeBase

A dedicated secondary Eufy account shared to the HomeBase is recommended. It
separates the controller's login session from the primary mobile-app account.

## Install

Clone the repository on the Pi and run:

```bash
sudo ./scripts/install.sh
```

The installer:

1. Installs missing Debian packages.
2. Creates the unprivileged `eufypanel` service account.
3. Installs the app under `/opt/eufy-panel`.
4. Installs hardened systemd units and setup helpers.
5. Starts only the safe demo provider.

### Configure the reverse proxy

Add [`deploy/nginx/eufy-location.conf`](deploy/nginx/eufy-location.conf) inside
the nginx `server` block that hosts Homepage, then validate and reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Adjust the public hostname in
[`deploy/homepage/services.example.yaml`](deploy/homepage/services.example.yaml),
then merge that service into Homepage's `services.yaml`. The widget refreshes
every 10 seconds and displays `Schedule · Home`, `Schedule · Away`, `Armed`, or
`Unavailable`, depending on the selected guard mode and active schedule rule.

### Configure weather

Edit `/etc/eufy-panel.env` and set a town or postcode. The optional country
filter makes the first geocoding result unambiguous:

```ini
WEATHER_LOCATION=Your town or postcode
WEATHER_COUNTRY_CODE=GB
WEATHER_LOCATION_LABEL=Your town
```

Restart the dashboard after changing the file:

```bash
sudo systemctl restart eufy-panel.service
```

For a precise location, leave `WEATHER_LOCATION` empty and set both
`WEATHER_LATITUDE` and `WEATHER_LONGITUDE`. Keep personal location values in
the Pi's environment file rather than committing them. Open-Meteo's free API is
appropriate for personal home automation and its data is provided under
CC BY 4.0; keep the attribution in the dashboard footer.

### Configure bin reminders

The reminder appears from Wednesday noon until Thursday noon. Configure a
known Thursday collection as the alternating schedule anchor:

```ini
BIN_COLLECTION_ANCHOR=2026-09-10
BIN_COLLECTION_ANCHOR_TYPE=black
BIN_TIMEZONE=Europe/London
BIN_REMINDER_START_HOUR=12
BIN_REMINDER_END_HOUR=12
```

`BIN_COLLECTION_ANCHOR_TYPE` accepts `black` or `blue-green`. Confirm the
anchor against the council calendar whenever the regular rotation changes;
bank-holiday exceptions are not fetched automatically.

To preview the next reminder outside its normal time window, open the panel
with `?preview=bins`. This is view-only and does not change the schedule.

### Select the country

Before signing in, edit `/etc/eufy-security-ws.env` and set `COUNTRY` to the
account's ISO 3166-1 alpha-2 country code:

```ini
COUNTRY=GB
```

Great Britain is `GB`, not `UK`.

### Configure Eufy credentials

Run the interactive root-only helper from the Pi terminal:

```bash
sudo eufy-panel-configure
```

The password is read with terminal echo disabled. It is not passed on the
command line, written into the web app, or returned to the browser.

If Eufy asks for a two-factor code:

```bash
sudo eufy-panel-verify
```

Reload the panel. The demo banner should disappear and the footer should show
`Eufy HomeBase`.

## Multiple HomeBases

The controller selects the only station on the account, or a single S380/T8030
when it can identify one. If the account exposes multiple possible stations,
set the serial locally in `/etc/eufy-panel.env`:

```ini
EUFY_STATION_SERIAL=T8030XXXXXXXXXXX
```

Do not commit that value to the repository.

## Operations

Common commands, updates, backups, and rollback are covered in
[Operations](docs/operations.md). Start with
[Troubleshooting](docs/troubleshooting.md) when the page reports that the bridge
or HomeBase is unavailable.

## Security

Read [Security](docs/security.md) before exposing the panel beyond a trusted
home LAN. In particular:

- Do not expose ports `8765` or `3001` directly to the internet.
- Do not commit `/etc/eufy-security-ws/` or `/var/lib/eufy-security-ws/`.
- Treat bridge logs and state backups as sensitive.
- Put authentication at the reverse proxy if untrusted clients can reach it.

## Development

The demo provider needs only Python's standard library:

```bash
PANEL_PROVIDER=demo PANEL_DATA_DIR=/tmp/eufy-panel-data \
  python3 app/server.py
```

Run the checks:

```bash
python3 -m py_compile app/server.py scripts/eufy-panel-verify
python3 -m unittest discover -s tests -v
node --check app/static/app.js
sh -n scripts/install.sh scripts/eufy-panel-configure
```

## Upstream projects

- [`bropat/eufy-security-ws`](https://github.com/bropat/eufy-security-ws)
- [`bropat/eufy-security-client`](https://github.com/bropat/eufy-security-client)

This project is not affiliated with or endorsed by Anker or Eufy.
