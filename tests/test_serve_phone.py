import sys
from pathlib import Path as _Path

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
    assert sp.parse_hostname_i("256.1.1.1 10.0.0.4") == ["10.0.0.4"]  # out-of-range rejected


def test_phone_urls_formats_and_dedupes():
    assert sp.phone_urls(["192.168.1.50", "192.168.1.50"], 8001) == [
        "http://192.168.1.50:8001"
    ]
    assert sp.phone_urls(["10.0.0.4"], 8001) == ["http://10.0.0.4:8001"]


def test_uvicorn_argv_binds_all_interfaces():
    argv = sp.uvicorn_argv("0.0.0.0", 8001)
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "uvicorn"]
    assert argv[3] == "api.server:app"
    assert "--host" in argv and argv[argv.index("--host") + 1] == "0.0.0.0"
    assert "--port" in argv and argv[argv.index("--port") + 1] == "8001"


def test_select_display_ips_prefers_windows_ip():
    assert sp.select_display_ips("192.168.1.50", ["172.20.1.2"]) == ["192.168.1.50"]
    assert sp.select_display_ips(None, ["172.20.1.2"]) == ["172.20.1.2"]


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
