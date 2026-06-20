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
