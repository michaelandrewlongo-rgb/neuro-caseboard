# Access the Caseboard GUI from your phone

The FastAPI app serves the built SPA **and** the API on one port, so you only need to
expose a single port. Default port is **8001** (8000 is unbindable on this WSL2 host).

## TL;DR (same Wi-Fi)

```bash
scripts/serve-phone.sh          # builds web/dist if missing, serves 0.0.0.0:8001
```

Then on your phone open the URL the banner prints (`http://<laptop-LAN-IP>:8001`).

## WSL2 (this machine) — pick ONE

WSL2 runs behind Windows NAT, so a `0.0.0.0` bind inside WSL is not LAN-reachable by itself.

- **(A) Mirrored networking (recommended, Win11 22H2+).** Create/edit `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  networkingMode=mirrored
  ```
  Then `wsl --shutdown` (from Windows) and restart WSL. Now the phone URL works as-is.

- **(B) Port-forward.** In an **elevated** PowerShell:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/wsl-portproxy.ps1 -Port 8001
  ```
  Find your PC's LAN IP with `ipconfig`, then open `http://<that-IP>:8001` on the phone.
  Tear down later with `... wsl-portproxy.ps1 -Port 8001 -Remove`.

## Dev mode (hot reload) on the phone

`npm run dev` now binds the Vite server to the LAN (`server.host: true`). Reach it at
`http://<laptop-LAN-IP>:5173`; the same WSL2 reachability options (A/B, but for port 5173)
apply. The Vite proxy forwards `/api` server-side, so there is still no CORS.

## Off-network / cellular (no LAN)

- **Quick public URL:** `cloudflared tunnel --url http://localhost:8001` → prints a temporary
  `https://*.trycloudflare.com` address (no account needed).
- **Persistent private:** install Tailscale on the laptop and phone, `tailscale up`, then open
  `http://<tailscale-100.x-IP>:8001`.

## Troubleshooting

- **Phone can't connect:** confirm both devices are on the same Wi-Fi; re-run option (B) — the
  WSL IP changes across reboots; check the Windows firewall allowed the port.
- **Port 8000 fails to bind:** use 8001 (WinNAT excluded range).
