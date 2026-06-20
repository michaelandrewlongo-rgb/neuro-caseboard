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
