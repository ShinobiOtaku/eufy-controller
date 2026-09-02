# Troubleshooting

## The page still says POC DEMO

Check the provider:

```bash
sudo grep '^PANEL_PROVIDER=' /etc/eufy-panel.env
```

It should be `PANEL_PROVIDER=eufy_ws`. Running
`sudo eufy-panel-configure` sets it after installing credentials.

## Eufy bridge is unavailable

```bash
systemctl is-active eufy-security-ws.service
sudo journalctl -u eufy-security-ws.service -n 100 --no-pager
sudo ss -ltn 'sport = :3001'
```

Port `3001` should listen only on `127.0.0.1`.

## Invalid country code

`COUNTRY` must be an ISO 3166-1 alpha-2 code. Use `GB` for Great Britain; `UK`
is rejected by the upstream client. Restart after changing it:

```bash
sudo systemctl restart eufy-security-ws.service
```

## Verification code required

```bash
sudo eufy-panel-verify
```

The helper submits the code over localhost without exposing it in the process
list. If the request has expired, restart the bridge to initiate a new login.

## CAPTCHA requested

The included helper handles two-factor codes, not CAPTCHA challenges. Stop the
bridge, confirm the account can sign in through the Eufy mobile app, and retry.
Consult the upstream `eufy-security-ws` documentation if Eufy continues to
require a CAPTCHA.

## No HomeBase was found

Confirm the configured account can see the HomeBase and has sufficient shared
permissions. A dedicated account generally needs the HomeBase shared to it with
administrative access.

## More than one HomeBase was found

Set `EUFY_STATION_SERIAL` in `/etc/eufy-panel.env` and restart the panel. Keep
the serial out of Git.

## The HomeBase is listed but mode changes time out

The container intentionally uses Docker bridge networking, so local UDP
auto-discovery is unavailable. The upstream client normally falls back to cloud
discovery. If that fails, add the HomeBase's fixed LAN address to
`/etc/eufy-security-ws.env` using the upstream format, then restart the bridge:

```ini
STATION_IP_ADDRESSES=STATION_SERIAL:HOMEBASE_IP
```

Treat both values as private deployment configuration and do not commit them.

## Schedule appears to be Home or Away

Schedule is a guard mode whose active timetable rule can itself be Home or Away.
The panel reads both values and should display Schedule whenever `guardMode=2`.
If it does not, collect the panel logs and bridge version before filing an issue.

## Homepage link works but health monitoring fails

The Homepage container may not share the host network. Either omit
`siteMonitor`, use a host-reachable address, or add an appropriate Docker host
gateway. Do not publish the panel backend to the wider network solely for the
monitor.
