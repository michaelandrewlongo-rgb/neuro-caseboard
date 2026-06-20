# Access the Caseboard GUI from your phone

The FastAPI app serves the built SPA **and** the API on one port, so you only need to
expose a single port. Default port is **8001** (8000 is unbindable on this WSL2 host).

Start the server first (leave it running):

```bash
scripts/serve-phone.sh          # builds web/dist if missing, serves 0.0.0.0:8001
```

> The served app must stay running for any of the options below — if the process exits,
> a phone (or a `tailscale serve` proxy) gets a connection error / 502. For an always-on
> setup, run it as a service or under a process manager rather than an ad-hoc shell.

## TL;DR (same Wi-Fi)

After `scripts/serve-phone.sh`, open the URL the banner prints (`http://<laptop-LAN-IP>:8001`)
on your phone. On WSL2 this also needs the reachability + firewall steps below.

## WSL2 (this machine) — make it LAN-reachable

WSL2 runs behind Windows NAT, so a `0.0.0.0` bind inside WSL is not LAN-reachable by itself.
Pick **one** of (A)/(B) for the network path, **and** open the Windows firewall (C).

- **(A) Mirrored networking (recommended, Win11 22H2+).** Create/edit `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  networkingMode=mirrored
  ```
  Then `wsl --shutdown` (from Windows) and restart WSL. WSL now shares the host's real
  LAN/VPN/Tailscale interfaces, so the LAN IP (e.g. `192.168.x.y`) is bound directly.

- **(B) Port-forward (NAT mode).** In an **elevated** PowerShell:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/wsl-portproxy.ps1 -Port 8001
  ```
  Find your PC's LAN IP with `ipconfig`, then open `http://<that-IP>:8001` on the phone.
  Tear down later with `... wsl-portproxy.ps1 -Port 8001 -Remove`.

- **(C) Open the Windows firewall (required even with mirrored networking).** With mirrored
  networking, inbound connections from your phone arrive at **Windows** and are dropped by the
  Windows Defender Firewall before reaching the WSL process — so the LAN/Tailscale IP appears
  "dead" even though the app is up. Confirm the symptom: from Windows, `http://127.0.0.1:8001`
  works but `http://<your-LAN-IP>:8001` fails. Fix, in an **elevated** PowerShell:
  ```powershell
  New-NetFirewallRule -DisplayName "Caseboard 8001" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8001
  ```
  (To avoid the firewall entirely, use the Tailscale `serve` option below.)

## Dev mode (hot reload) on the phone

`npm run dev` now binds the Vite server to the LAN (`server.host: true`). Reach it at
`http://<laptop-LAN-IP>:5173`; the same WSL2 reachability + firewall steps (for port 5173)
apply. The Vite proxy forwards `/api` server-side, so there is still no CORS.

## Tailscale (recommended — private, works on any network, no firewall changes)

Tailscale gives the phone access from anywhere with no firewall rule. **Use `tailscale serve`,
not the raw `http://100.x.y.z:8001` address** — on WSL with mirrored networking, Tailscale runs
on **Windows** and the raw Tailscale IP:port is blocked by the Windows firewall exactly like the
LAN IP. `tailscale serve` instead has Windows tailscaled accept the connection and proxy it to
the app over loopback (`127.0.0.1:8001`), which is never firewall-blocked.

1. Install Tailscale on the laptop (here: on Windows) and the phone; sign both into the same
   tailnet and confirm the phone shows the laptop node as **online** (`tailscale status`).
2. Expose the app **privately on the tailnet** on a dedicated port (here `8443`):
   ```powershell
   tailscale serve --bg --yes --https=8443 http://127.0.0.1:8001
   ```
   - **Use a port that is NOT Funnel-enabled.** `AllowFunnel` is keyed by host:**port**, so every
     handler on a Funnel port is public on the internet. This server has no auth — keep it on a
     `serve` (tailnet-only) port. Verify with `tailscale serve status --json` that your app's port
     is **absent** from `AllowFunnel`.
3. On the phone, open the **MagicDNS name** (not the IP — the TLS cert is issued for the name):
   ```
   https://<node-name>.<tailnet>.ts.net:8443/
   ```
4. Undo later with: `tailscale serve --https=8443 off`.

> If the page won't load over Tailscale: (a) confirm the phone is connected and the laptop node
> is online; (b) confirm the app is running — from Windows, `http://127.0.0.1:8001` must return
> 200, since that's what `serve` proxies to; (c) use the MagicDNS name, not the `100.x` IP.

## Off-network without Tailscale

- **Quick public URL:** `cloudflared tunnel --url http://localhost:8001` → prints a temporary
  `https://*.trycloudflare.com` address (no account needed).
  **⚠️ WARNING: this server has NO authentication.** Anyone who has the public
  `*.trycloudflare.com` URL can reach *all* of your data — there is no login, token, or IP
  allow-list in front of it. Only use a public tunnel **briefly and intentionally**, and stop
  `cloudflared` (Ctrl-C) the moment you are done. Prefer the private Tailscale option above.

## Troubleshooting

- **Phone can't connect (LAN):** confirm both devices are on the same Wi-Fi; on WSL2 confirm the
  firewall rule (C) — and that the WSL IP hasn't changed across reboots (re-run option B); from
  Windows, `127.0.0.1:8001` working but `<LAN-IP>:8001` failing means the firewall is the blocker.
- **Tailscale URL errors / 502 / "server stopped responding":** the app (proxy target) probably
  isn't running — restart `scripts/serve-phone.sh` and confirm `127.0.0.1:8001` returns 200.
- **Certificate warning over Tailscale:** you used the `100.x` IP — use the `*.ts.net` MagicDNS
  name instead.
- **Port 8000 fails to bind:** use 8001 (WinNAT excluded range).
