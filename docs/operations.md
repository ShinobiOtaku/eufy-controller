# Operations

## Service status

```bash
systemctl status eufy-panel.service
systemctl status eufy-security-ws.service
curl -fsS http://127.0.0.1:8765/api/health
```

A live health response looks like:

```json
{"ok":true,"provider":"Eufy HomeBase","live":true}
```

## Logs

```bash
sudo journalctl -u eufy-panel.service -n 100 --no-pager
sudo journalctl -u eufy-security-ws.service -n 100 --no-pager
```

Bridge logs can contain device or account metadata. Review them before sharing.

## Change credentials

Run the interactive helper again:

```bash
sudo eufy-panel-configure
```

It replaces the root-only secret files and restarts the bridge.

## Return to demo mode

Edit `/etc/eufy-panel.env` and set:

```ini
PANEL_PROVIDER=demo
```

Then restart the panel:

```bash
sudo systemctl restart eufy-panel.service
```

This does not delete credentials or bridge state.

## Update the application

Pull and rerun the installer:

```bash
git pull --ff-only
sudo ./scripts/install.sh
```

Existing environment files are preserved.

## Update the bridge image

The systemd unit pins the upstream image by digest for reproducibility. To
upgrade deliberately:

1. Read the upstream release notes.
2. Pull the desired tag.
3. Resolve its repository digest with `docker image inspect`.
4. Replace the digest in `deploy/systemd/eufy-security-ws.service`.
5. Run the installer and restart the bridge.

```bash
sudo systemctl restart eufy-security-ws.service
```

Commit the digest change so deployments remain reproducible.

## Backup

Back up these paths only into encrypted storage:

- `/etc/eufy-panel.env`
- `/etc/eufy-security-ws.env`
- `/etc/eufy-security-ws/`
- `/var/lib/eufy-security-ws/`

The last two contain credentials or reusable session material. They must never
be committed.

## Manual removal

Stop and disable both units, then remove the installed units, helpers, and app.
Preserve `/etc/eufy-security-ws/` and `/var/lib/eufy-security-ws/` unless you
explicitly intend to destroy credentials and session state.

```bash
sudo systemctl disable --now eufy-panel.service eufy-security-ws.service
```

Reload systemd after removing unit files:

```bash
sudo systemctl daemon-reload
```
