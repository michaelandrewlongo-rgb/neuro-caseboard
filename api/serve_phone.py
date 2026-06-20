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
