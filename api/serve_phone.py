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
