# Run ONCE in an elevated (Admin) Windows PowerShell. Forwards the Windows port
# (reachable on the Tailscale interface) to the WSL2 server, and opens the firewall.
param([int]$Port = 8000)

$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
if (-not $wslIp) { Write-Error "Could not determine WSL2 IP (is WSL running?)"; exit 1 }
Write-Host "WSL2 IP: $wslIp  Port: $Port"

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port `
  connectaddress=$wslIp connectport=$Port

New-NetFirewallRule -DisplayName "Neuro RAG $Port" -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction SilentlyContinue | Out-Null

Write-Host "Done. From your phone (on Tailscale) open: http://<this-PC-tailscale-ip>:$Port"
Write-Host "NOTE: the WSL2 IP changes on reboot — re-run this script if the phone can't connect."
