$ErrorActionPreference = "Continue"

$logPath = Join-Path $PSScriptRoot "set_ethernet_dhcp_keep_dns_admin.log"
Start-Transcript -Path $logPath -Append | Out-Null

$adapterName = "Ethernet"
Write-Host "Setting $adapterName to DHCP IP with reliable DNS..."

netsh interface ipv4 set address name="$adapterName" source=dhcp
netsh interface ipv4 set dnsservers name="$adapterName" static 8.8.8.8 primary
netsh interface ipv4 add dnsservers name="$adapterName" 1.1.1.1 index=2
ipconfig /release "$adapterName"
ipconfig /renew "$adapterName"
ipconfig /flushdns

Write-Host "Current Ethernet configuration:"
ipconfig /all

Stop-Transcript | Out-Null
Write-Host "Done. Log: $logPath"
