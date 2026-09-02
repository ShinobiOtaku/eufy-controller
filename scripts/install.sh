#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo ./scripts/install.sh" >&2
    exit 1
fi

repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
packages=''

command -v python3 >/dev/null 2>&1 || packages="$packages python3"
command -v docker >/dev/null 2>&1 || packages="$packages docker.io"
if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import websockets' >/dev/null 2>&1 || packages="$packages python3-websockets"
else
    packages="$packages python3-websockets"
fi

if [ -n "$packages" ]; then
    apt-get update
    # shellcheck disable=SC2086
    apt-get install -y $packages
fi

systemctl enable --now docker.service

if ! id -u eufypanel >/dev/null 2>&1; then
    useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin eufypanel
fi

install -d -o root -g root -m 0755 /opt/eufy-panel /opt/eufy-panel/static
install -d -o eufypanel -g eufypanel -m 0700 /var/lib/eufy-panel
install -d -o root -g root -m 0700 /var/lib/eufy-security-ws

install -o root -g root -m 0755 "$repo_dir/app/server.py" /opt/eufy-panel/server.py
install -o root -g root -m 0644 \
    "$repo_dir/app/static/index.html" \
    "$repo_dir/app/static/app.css" \
    "$repo_dir/app/static/app.js" \
    "$repo_dir/app/static/favicon.svg" \
    /opt/eufy-panel/static/

if [ ! -e /etc/eufy-panel.env ]; then
    install -o root -g root -m 0600 \
        "$repo_dir/config/eufy-panel.env.example" /etc/eufy-panel.env
fi
if [ ! -e /etc/eufy-security-ws.env ]; then
    install -o root -g root -m 0644 \
        "$repo_dir/config/eufy-security-ws.env.example" /etc/eufy-security-ws.env
fi

install -o root -g root -m 0644 \
    "$repo_dir/deploy/systemd/eufy-panel.service" \
    /etc/systemd/system/eufy-panel.service
install -o root -g root -m 0644 \
    "$repo_dir/deploy/systemd/eufy-security-ws.service" \
    /etc/systemd/system/eufy-security-ws.service
install -o root -g root -m 0755 \
    "$repo_dir/scripts/eufy-panel-configure" /usr/local/sbin/eufy-panel-configure
install -o root -g root -m 0755 \
    "$repo_dir/scripts/eufy-panel-verify" /usr/local/sbin/eufy-panel-verify

systemctl daemon-reload
systemctl enable --now eufy-panel.service

echo "Installed the panel in safe demo mode on http://127.0.0.1:8765/"
echo "Next: add the nginx location, then run sudo eufy-panel-configure"
