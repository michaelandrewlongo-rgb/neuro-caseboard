# Serve the GUI on a Phone — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the Neuro·Caseboard web GUI (already served by `api/server.py` together with the API) reachable from a phone on the same network as the laptop, with a one-command launcher and a runbook that handles this machine's WSL2 networking.

**Architecture:** The FastAPI app already serves the built SPA from `web/dist` at `/` **and** the `/api/*` endpoints on a single origin (`api/server.py` lines ~672–713). Nothing in the browser is cross-origin, so there is **no CORS work**. The only blockers to phone access are (1) the process binds to `127.0.0.1` (loopback) instead of `0.0.0.0`, and (2) this is WSL2, whose NAT hides a `0.0.0.0` bind from other LAN devices unless mirrored networking or a Windows `netsh portproxy` rule is in place. We add a small **functional-core** Python module (`api/serve_phone.py`) holding pure, unit-tested helpers (WSL detection, IP/URL formatting, command-string builders), a thin launcher (`main()` + `scripts/serve-phone.sh`) that binds `0.0.0.0` and prints a reachability banner, a Windows PowerShell helper for port-forwarding, a Vite dev-server LAN-host toggle, and a runbook doc.

**Tech Stack:** Python 3.12 (stdlib only — `socket`, `subprocess`, `pathlib`, `shutil`), FastAPI/uvicorn (already deps), pytest, Vite/TypeScript (config only), PowerShell (Windows-side helper script), Bash (launcher wrapper).

## Global Constraints

- **Python: stdlib only** for `api/serve_phone.py` — no new dependencies (uvicorn is already a dep and is only invoked via `subprocess`/`os.execvp`, never a hard import in the testable core).
- **Default port is `8001`**, never `8000` — port 8000 is in a Windows WinNAT excluded range on this host and is unbindable (documented in `web/vite.config.ts:6-7`).
- **No CORS changes** — the SPA and `/api` are same-origin via the unified server (prod) and the Vite proxy (dev); introducing CORS would be wrong and would widen the (intentionally auth-less, local-first) surface.
- **Functional-core / imperative-shell:** all logic that parses command output or builds command strings must be a **pure function** taking its input as an argument (unit-tested); functions that actually shell out are thin wrappers with no branching logic and are not unit-tested.
- **All new pytest tests live in `tests/test_serve_phone.py`** (one file) so the loop harness — `npm --prefix web run build` + `python3 -m pytest tests/test_serve_phone.py tests/test_server_spa.py -q` — exercises every change.
- **Tests must set `NEURO_CASEBOARD_SKIP_DOTENV=1`** is NOT required here (these tests don't load engine config), but tests must not depend on network access, the actual OS being WSL, or `powershell.exe`/`netsh` being present — inject raw text into the pure functions instead.

---

### Task 1: Functional core — WSL detection, IP/URL formatting, command builders

**Files:**
- Create: `api/serve_phone.py`
- Test: `tests/test_serve_phone.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces (later tasks rely on these exact signatures):
  - `is_wsl(osrelease: str | None = None) -> bool` — pure when `osrelease` is passed; reads `/proc/sys/kernel/osrelease` when `None`.
  - `parse_hostname_i(output: str) -> list[str]` — split the space-separated output of `hostname -I` into IPv4 strings (drop IPv6 / blanks).
  - `phone_urls(ips: list[str], port: int) -> list[str]` — `["http://{ip}:{port}", ...]`, de-duplicated, order-preserving.
  - `uvicorn_argv(host: str, port: int, app: str = "api.server:app") -> list[str]` — `["uvicorn", app, "--host", host, "--port", str(port)]`.
  - `wsl_portproxy_commands(port: int, wsl_ip: str, *, rule_name: str = "Caseboard") -> dict[str, str]` — keys `add`, `delete`, `firewall_add`, `firewall_delete`, `show` mapping to exact Windows command strings.
  - `DEFAULT_PORT: int = 8001`.

- [x] **Step 1: Write the failing tests**

```python
# tests/test_serve_phone.py
from api import serve_phone as sp


def test_default_port_is_8001():
    assert sp.DEFAULT_PORT == 8001


def test_is_wsl_detects_microsoft_osrelease():
    assert sp.is_wsl("6.6.87.2-microsoft-standard-WSL2") is True
    assert sp.is_wsl("5.15.0-generic") is False
    assert sp.is_wsl("") is False


def test_parse_hostname_i_keeps_ipv4_only():
    assert sp.parse_hostname_i("172.20.1.2 fe80::1 \n") == ["172.20.1.2"]
    assert sp.parse_hostname_i("192.168.1.50 10.0.0.4") == ["192.168.1.50", "10.0.0.4"]
    assert sp.parse_hostname_i("   ") == []


def test_phone_urls_formats_and_dedupes():
    assert sp.phone_urls(["192.168.1.50", "192.168.1.50"], 8001) == [
        "http://192.168.1.50:8001"
    ]
    assert sp.phone_urls(["10.0.0.4"], 8001) == ["http://10.0.0.4:8001"]


def test_uvicorn_argv_binds_all_interfaces():
    argv = sp.uvicorn_argv("0.0.0.0", 8001)
    assert argv[:2] == ["uvicorn", "api.server:app"]
    assert "--host" in argv and argv[argv.index("--host") + 1] == "0.0.0.0"
    assert "--port" in argv and argv[argv.index("--port") + 1] == "8001"


def test_wsl_portproxy_commands_have_consistent_port_and_ip():
    cmds = sp.wsl_portproxy_commands(8001, "172.20.1.2")
    assert "listenport=8001" in cmds["add"]
    assert "connectport=8001" in cmds["add"]
    assert "connectaddress=172.20.1.2" in cmds["add"]
    assert "listenaddress=0.0.0.0" in cmds["add"]
    assert "listenport=8001" in cmds["delete"]
    assert "New-NetFirewallRule" in cmds["firewall_add"]
    assert "8001" in cmds["firewall_add"]
    assert "Remove-NetFirewallRule" in cmds["firewall_delete"]
    assert "portproxy" in cmds["show"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.serve_phone'` (collection error).

- [x] **Step 3: Write minimal implementation**

```python
# api/serve_phone.py
"""Helpers to serve the Caseboard GUI+API so a phone on the same network can reach it.

Functional core: every function here that parses output or builds a command string is
PURE (its inputs are arguments), so it is unit-tested without touching the real OS,
`hostname`, `netsh`, or `powershell.exe`. The thin IO wrappers / launcher live in the
companion functions below and in `main()` (Task 2).
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_PORT = 8001
APP = "api.server:app"


def is_wsl(osrelease: str | None = None) -> bool:
    """True when running under WSL. Pass `osrelease` to keep this pure (testable)."""
    if osrelease is None:
        try:
            osrelease = Path("/proc/sys/kernel/osrelease").read_text()
        except OSError:
            return False
    return "microsoft" in osrelease.lower() or "wsl" in osrelease.lower()


def parse_hostname_i(output: str) -> list[str]:
    """Extract IPv4 addresses from the space-separated output of `hostname -I`."""
    out: list[str] = []
    for tok in output.split():
        # IPv4 = four dot-separated decimal octets; this drops IPv6 (which contain ':').
        parts = tok.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            out.append(tok)
    return out


def phone_urls(ips: list[str], port: int) -> list[str]:
    """Build de-duplicated http URLs (order-preserving) for the given host IPs."""
    seen: set[str] = set()
    urls: list[str] = []
    for ip in ips:
        url = f"http://{ip}:{port}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def uvicorn_argv(host: str, port: int, app: str = APP) -> list[str]:
    """argv for launching uvicorn bound to `host`."""
    return ["uvicorn", app, "--host", host, "--port", str(port)]


def wsl_portproxy_commands(port: int, wsl_ip: str, *, rule_name: str = "Caseboard") -> dict[str, str]:
    """Windows-side commands (run elevated) to forward LAN :port -> WSL :port + open the firewall."""
    add = (
        f"netsh interface portproxy add v4tov4 "
        f"listenaddress=0.0.0.0 listenport={port} "
        f"connectaddress={wsl_ip} connectport={port}"
    )
    delete = (
        f"netsh interface portproxy delete v4tov4 "
        f"listenaddress=0.0.0.0 listenport={port}"
    )
    firewall_add = (
        f"New-NetFirewallRule -DisplayName '{rule_name} {port}' -Direction Inbound "
        f"-Action Allow -Protocol TCP -LocalPort {port}"
    )
    firewall_delete = f"Remove-NetFirewallRule -DisplayName '{rule_name} {port}'"
    show = "netsh interface portproxy show v4tov4"
    return {
        "add": add,
        "delete": delete,
        "firewall_add": firewall_add,
        "firewall_delete": firewall_delete,
        "show": show,
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: PASS (6 tests).

- [x] **Step 5: Commit**

```bash
git add api/serve_phone.py tests/test_serve_phone.py
git commit -m "loop step 0: functional core for phone serving (WSL detect, IP/URL/command builders)"
```

---

### Task 2: Launcher — `main()` reachability banner + `scripts/serve-phone.sh`

**Files:**
- Modify: `api/serve_phone.py` (add `local_ipv4_addresses()`, `windows_lan_ip()`, `reachability_banner()`, `main()`)
- Create: `scripts/serve-phone.sh`
- Test: `tests/test_serve_phone.py` (extend)

**Interfaces:**
- Consumes: `is_wsl`, `parse_hostname_i`, `phone_urls`, `uvicorn_argv`, `wsl_portproxy_commands`, `DEFAULT_PORT` (Task 1).
- Produces:
  - `reachability_banner(*, port: int, is_wsl_host: bool, ips: list[str], wsl_ip: str | None) -> str` — pure; the multi-line text printed before launch. MUST contain each phone URL, and when `is_wsl_host` is True MUST contain the `netsh ... portproxy` setup line and a "mirrored networking" hint.
  - `main(argv: list[str] | None = None) -> int` — parses `--port` / `--no-banner`, prints the banner, then `os.execvp`s uvicorn bound to `0.0.0.0`. (Exec is only reached in real runs; tests call `reachability_banner` directly and never `main`.)

- [x] **Step 1: Write the failing tests**

```python
# append to tests/test_serve_phone.py
def test_reachability_banner_lists_urls_native():
    text = sp.reachability_banner(
        port=8001, is_wsl_host=False, ips=["192.168.1.50"], wsl_ip=None
    )
    assert "http://192.168.1.50:8001" in text
    assert "netsh" not in text  # native host: no Windows port-forward needed


def test_reachability_banner_includes_wsl_portproxy_and_mirrored_hint():
    text = sp.reachability_banner(
        port=8001, is_wsl_host=True, ips=["192.168.1.50"], wsl_ip="172.20.1.2"
    )
    assert "netsh interface portproxy add" in text
    assert "connectaddress=172.20.1.2" in text
    assert "listenport=8001" in text
    assert "mirrored" in text.lower()
    assert "scripts/wsl-portproxy.ps1" in text  # points at the helper from Task 3
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: FAIL — `AttributeError: module 'api.serve_phone' has no attribute 'reachability_banner'`.

- [x] **Step 3: Write minimal implementation**

```python
# append to api/serve_phone.py
import os
import socket
import subprocess


def local_ipv4_addresses() -> list[str]:
    """Best-effort primary outbound IPv4 of this host (the WSL VM IP under WSL)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packets are sent for UDP connect
        return [s.getsockname()[0]]
    except OSError:
        return []
    finally:
        s.close()


def windows_lan_ip() -> str | None:
    """Under WSL (NAT mode), ask Windows for its LAN IPv4 via powershell.exe. None on failure."""
    try:
        out = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "(Get-NetIPAddress -AddressFamily IPv4 | "
                "Where-Object {$_.PrefixOrigin -ne 'WellKnown' -and "
                "$_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1'} | "
                "Select-Object -First 1).IPAddress",
            ],
            capture_output=True, text=True, timeout=10,
        )
        ip = out.stdout.strip()
        return ip or None
    except (OSError, subprocess.SubprocessError):
        return None


def reachability_banner(*, port: int, is_wsl_host: bool, ips: list[str], wsl_ip: str | None) -> str:
    lines = ["", "=" * 64, "  Neuro·Caseboard — serving for phone access", "=" * 64]
    urls = phone_urls(ips, port)
    if urls:
        lines.append("  On your phone (same Wi-Fi) open:")
        lines += [f"    {u}" for u in urls]
    else:
        lines.append("  Could not determine a LAN IP — run `ip addr` / `ipconfig`.")
    if is_wsl_host:
        lines += [
            "",
            "  WSL2 detected. A LAN phone can reach this ONLY if either:",
            "   (A) WSL mirrored networking is on  (recommended; %UserProfile%\\.wslconfig:",
            "       [wsl2]  networkingMode=mirrored ), then the URLs above work as-is; or",
            "   (B) you add a Windows port-forward (run in an *elevated* PowerShell):",
        ]
        if wsl_ip:
            cmds = wsl_portproxy_commands(port, wsl_ip)
            lines += [f"       {cmds['add']}", f"       {cmds['firewall_add']}"]
        lines.append("       (or just run: scripts/wsl-portproxy.ps1 -Port "
                     f"{port}  from an elevated PowerShell)")
    lines += ["=" * 64, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Serve the Caseboard GUI+API for phone access.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-banner", action="store_true")
    args = parser.parse_args(argv)

    wsl = is_wsl()
    ips = local_ipv4_addresses()
    win_ip = windows_lan_ip() if wsl else None
    wsl_ip = ips[0] if ips else None
    # Prefer the Windows LAN IP for the printed phone URL when under WSL NAT.
    display_ips = [win_ip] if win_ip else ips
    if not args.no_banner:
        print(reachability_banner(port=args.port, is_wsl_host=wsl, ips=display_ips, wsl_ip=wsl_ip))
    argv2 = uvicorn_argv(args.host, args.port)
    os.execvp(argv2[0], argv2)  # replaces this process; never returns on success
    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: PASS (8 tests).

- [x] **Step 5: Create the shell launcher**

```bash
# scripts/serve-phone.sh
#!/usr/bin/env bash
# Build the SPA if missing, then serve GUI+API on 0.0.0.0 so a phone can reach it.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8001}"
if [ ! -f web/dist/index.html ]; then
  echo "web/dist not found — building the SPA (npm --prefix web run build)…"
  npm --prefix web run build
fi
exec python3 -m api.serve_phone --port "$PORT"
```

- [x] **Step 6: Make it executable and commit**

```bash
chmod +x scripts/serve-phone.sh
git add api/serve_phone.py tests/test_serve_phone.py scripts/serve-phone.sh
git commit -m "loop step 1: serve-phone launcher (0.0.0.0 bind, reachability banner, build-if-missing wrapper)"
```

---

### Task 3: Windows port-forward helper `scripts/wsl-portproxy.ps1`

**Files:**
- Create: `scripts/wsl-portproxy.ps1`
- Test: `tests/test_serve_phone.py` (extend — consistency check that the script matches the command-builder)

**Interfaces:**
- Consumes: `wsl_portproxy_commands`, `DEFAULT_PORT` (Task 1).
- Produces: a parameterized PowerShell script with `-Port` (default 8001), `-Remove`, and `-Status` switches that auto-detects the WSL IP via `wsl hostname -I`.

- [x] **Step 1: Write the failing test**

```python
# append to tests/test_serve_phone.py
from pathlib import Path as _Path


def test_wsl_portproxy_ps1_exists_and_is_consistent():
    ps1 = _Path("scripts/wsl-portproxy.ps1")
    assert ps1.is_file(), "scripts/wsl-portproxy.ps1 must exist"
    text = ps1.read_text()
    # Default port must match the module default.
    assert f"= {sp.DEFAULT_PORT}" in text or f"={sp.DEFAULT_PORT}" in text
    # Must use the same Windows primitives the helper documents.
    assert "netsh interface portproxy add" in text
    assert "New-NetFirewallRule" in text
    assert "Remove-NetFirewallRule" in text
    # Auto-detect the WSL IP rather than hardcoding it.
    assert "wsl" in text.lower() and "hostname -I" in text
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_serve_phone.py::test_wsl_portproxy_ps1_exists_and_is_consistent -q`
Expected: FAIL — `AssertionError: scripts/wsl-portproxy.ps1 must exist`.

- [x] **Step 3: Write the PowerShell helper**

```powershell
# scripts/wsl-portproxy.ps1
# Forward a Windows LAN port to the WSL2 VM so a phone on the same network can reach
# the Caseboard GUI+API. Run in an *elevated* PowerShell (Run as Administrator).
#   Setup : powershell -ExecutionPolicy Bypass -File scripts\wsl-portproxy.ps1 -Port 8001
#   Status: ...\wsl-portproxy.ps1 -Status
#   Remove: ...\wsl-portproxy.ps1 -Port 8001 -Remove
param(
    [int]$Port = 8001,
    [switch]$Remove,
    [switch]$Status
)

$ruleName = "Caseboard $Port"

if ($Status) {
    netsh interface portproxy show v4tov4
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    exit 0
}

if ($Remove) {
    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    Write-Host "Removed port-proxy and firewall rule for port $Port."
    exit 0
}

# Auto-detect the current WSL2 IP (changes across reboots in NAT mode).
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
if (-not $wslIp) { Write-Error "Could not determine WSL IP via 'wsl hostname -I'."; exit 1 }

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port connectaddress=$wslIp connectport=$Port
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
}
Write-Host "Forwarding LAN :$Port -> WSL ${wslIp}:$Port and opened the firewall."
Write-Host "On your phone open: http://<this-PC-LAN-IP>:$Port   (run 'ipconfig' to find it)"
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: PASS (9 tests).

- [x] **Step 5: Commit**

```bash
git add scripts/wsl-portproxy.ps1 tests/test_serve_phone.py
git commit -m "loop step 2: Windows wsl-portproxy.ps1 helper (setup/remove/status, auto WSL IP)"
```

---

### Task 4: Vite dev LAN host + runbook doc + pointer

**Files:**
- Modify: `web/vite.config.ts:18-26` (set `server.host: true`)
- Create: `docs/SERVE_ON_PHONE.md`
- Modify: `CLAUDE.md` (append a one-line pointer under the Web console section)
- Test: `tests/test_serve_phone.py` (extend — doc consistency)

**Interfaces:**
- Consumes: all of the above (the doc references `scripts/serve-phone.sh`, `scripts/wsl-portproxy.ps1`, port 8001).
- Produces: nothing consumed by later tasks (final task).

- [x] **Step 1: Write the failing test**

```python
# append to tests/test_serve_phone.py
def test_runbook_doc_exists_and_references_helpers():
    doc = _Path("docs/SERVE_ON_PHONE.md")
    assert doc.is_file(), "docs/SERVE_ON_PHONE.md must exist"
    text = doc.read_text()
    assert "scripts/serve-phone.sh" in text
    assert "scripts/wsl-portproxy.ps1" in text
    assert "8001" in text
    assert "mirrored" in text.lower()          # the recommended WSL path
    assert "tailscale" in text.lower() or "cloudflared" in text.lower()  # off-network fallback


def test_vite_config_enables_lan_host():
    cfg = _Path("web/vite.config.ts").read_text()
    assert "host: true" in cfg
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_serve_phone.py -q`
Expected: FAIL — doc assertion (`docs/SERVE_ON_PHONE.md must exist`) and `host: true` assertion.

- [x] **Step 3a: Enable the Vite dev server on the LAN**

Edit `web/vite.config.ts` `server` block to add `host: true` (binds the dev server to all interfaces so `npm run dev` is reachable at `http://<laptop-ip>:5173`; the existing `/api` proxy keeps the browser single-origin, so still no CORS):

```ts
  server: {
    host: true,        // expose the dev server on the LAN (phone access); proxy keeps one origin
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
```

- [x] **Step 3b: Write the runbook**

```markdown
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
  powershell -ExecutionPolicy Bypass -File scripts\wsl-portproxy.ps1 -Port 8001
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
```

- [x] **Step 3c: Add the CLAUDE.md pointer**

Append under the `## Web console (web/)` section of `CLAUDE.md`:

```markdown
- **Phone access:** `scripts/serve-phone.sh` serves the SPA+API on `0.0.0.0:8001` and prints a
  reachability banner. WSL2 needs mirrored networking or `scripts/wsl-portproxy.ps1` (elevated).
  Full runbook: `docs/SERVE_ON_PHONE.md`.
```

- [x] **Step 4: Run the full harness to verify it passes**

Run: `npm --prefix web run build && python3 -m pytest tests/test_serve_phone.py tests/test_server_spa.py -q`
Expected: build succeeds; all serve_phone tests + 3 SPA tests PASS.

- [x] **Step 5: Commit**

```bash
git add web/vite.config.ts docs/SERVE_ON_PHONE.md CLAUDE.md tests/test_serve_phone.py
git commit -m "loop step 3: Vite LAN host + phone-access runbook + CLAUDE pointer"
```

---

## Self-Review

**Spec coverage:**
- "served by my laptop" → Task 2 launcher binds `0.0.0.0`; serves existing unified SPA+API. ✔
- "access the GUI on my phone" → Task 1/2 print phone URLs; Task 3 WSL port-forward; Task 4 mirrored-mode + dev-mode + tunnel fallbacks + runbook. ✔
- This machine is WSL2 (the actual blocker) → Tasks 1–4 all address WSL2 NAT explicitly. ✔
- No CORS regression / local-first preserved → Global Constraints + single-origin design. ✔

**Placeholder scan:** No TBD/TODO; every code and test step has concrete content. ✔

**Type consistency:** `is_wsl`, `parse_hostname_i`, `phone_urls`, `uvicorn_argv`, `wsl_portproxy_commands`, `reachability_banner`, `main`, `DEFAULT_PORT` are used with identical signatures across tasks; the `.ps1` rule name (`Caseboard <port>`) matches `wsl_portproxy_commands`' `rule_name` default. ✔

**Harness:** All new tests live in `tests/test_serve_phone.py`; the loop harness is updated to `npm --prefix web run build` + `python3 -m pytest tests/test_serve_phone.py tests/test_server_spa.py -q`. ✔
