# Security

## Trust model

This is a trusted-LAN control panel, not an internet-facing security product.
There is no application PIN or user authentication. Anyone who can reach the
page can select Schedule or Away.

The restricted two-mode backend limits impact: Home, Disarmed, and arbitrary
Eufy commands are not accepted. That is not a substitute for network access
control.

## Network exposure

- Keep the Python service on `127.0.0.1:8765`.
- Keep the bridge on `127.0.0.1:3001`.
- Expose only the nginx route to the trusted LAN.
- Do not add router port forwarding for the panel.
- Add reverse-proxy authentication or a VPN before allowing untrusted clients.

## Credentials

`eufy-panel-configure` stores the account name and password in separate
root-owned files with mode `0600`. Docker receives them through read-only secret
file mounts. They do not appear in the container command line or browser API.

The upstream bridge creates reusable cloud session data under
`/var/lib/eufy-security-ws`. Protect that directory like a password.

Use a dedicated Eufy account shared only to the required HomeBase when
possible. Apply the least Eufy permissions that still permit guard-mode
changes.

## Browser/API protections

- State-changing requests require a session-bound CSRF token.
- Session cookies are `HttpOnly` and `SameSite=Strict`.
- Responses set a restrictive Content Security Policy.
- The browser receives only display-ready weather, panel status, and station
  mode information. Weather coordinates are not included in API responses.

## Weather privacy

The Pi sends the configured location search or coordinates to Open-Meteo. The
free API may retain server logs containing coordinates for up to 90 days. Use a
nearby town rather than precise coordinates if that privacy tradeoff is
preferable. The phone browser connects only to the local dashboard.

The default deployment uses HTTP because it targets a private LAN. Configure
TLS at nginx if the network is not fully trusted.

## Container and service hardening

The bridge container:

- has all Linux capabilities dropped;
- uses `no-new-privileges`;
- publishes its WebSocket port only on loopback;
- runs a pinned image digest.

The Python service runs as an unprivileged system account with a read-only
system view and a narrow writable data directory.

## Before publishing logs or reports

Remove email addresses, account IDs, authentication tokens, HomeBase serials,
device names, IP addresses, and persistent bridge data. The repository's
`.gitignore` is a guardrail, not a secret scanner.
