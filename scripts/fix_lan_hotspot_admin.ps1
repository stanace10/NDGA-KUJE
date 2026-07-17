$ErrorActionPreference = "Continue"

$logPath = Join-Path $PSScriptRoot "fix_lan_hotspot_admin.log"
Start-Transcript -Path $logPath -Append | Out-Null

Write-Host "NDGA LAN/Hotspot repair started..."

$rules = @(
    @{ Name = "NDGA LAN HTTP 80"; Port = 80 },
    @{ Name = "NDGA LAN HTTPS 443"; Port = 443 },
    @{ Name = "NDGA Grafana 3000"; Port = 3000 }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -DisplayName $rule.Name -Enabled True -Profile Any -Direction Inbound -Action Allow
        Get-NetFirewallPortFilter -AssociatedNetFirewallRule $existing | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $rule.Port
        Write-Host "Updated firewall rule: $($rule.Name)"
    } else {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $rule.Port -Profile Any | Out-Null
        Write-Host "Created firewall rule: $($rule.Name)"
    }
}

$hotspot = Get-NetAdapter -Name "Local Area Connection* 2" -ErrorAction SilentlyContinue
if ($hotspot) {
    Write-Host "Hotspot adapter found: $($hotspot.Name) index $($hotspot.ifIndex)"

    Get-NetIPAddress -InterfaceIndex $hotspot.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -ne "192.168.137.1" } |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

    $has137 = Get-NetIPAddress -InterfaceIndex $hotspot.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq "192.168.137.1" }
    if (-not $has137) {
        New-NetIPAddress -InterfaceIndex $hotspot.ifIndex -IPAddress "192.168.137.1" -PrefixLength 24 -ErrorAction SilentlyContinue | Out-Null
        Write-Host "Set hotspot adapter IP to 192.168.137.1/24"
    }

    $route137 = Get-NetRoute -DestinationPrefix "192.168.137.0/24" -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceIndex -eq $hotspot.ifIndex }
    if (-not $route137) {
        New-NetRoute -DestinationPrefix "192.168.137.0/24" -InterfaceIndex $hotspot.ifIndex -NextHop "0.0.0.0" -RouteMetric 25 -ErrorAction SilentlyContinue | Out-Null
        Write-Host "Added hotspot route 192.168.137.0/24"
    }
}

foreach ($serviceName in @("WlanSvc", "SharedAccess", "icssvc")) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service) {
        try {
            Restart-Service -Name $serviceName -Force -ErrorAction Stop
            Write-Host "Restarted service: $serviceName"
        } catch {
            Write-Host "Could not restart $serviceName: $($_.Exception.Message)"
            Start-Service -Name $serviceName -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Current IPv4 addresses:"
Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, InterfaceIndex, IPAddress, PrefixLength, AddressState | Format-Table -AutoSize

Write-Host "Current route entries for NDGA LAN/hotspot:"
Get-NetRoute -AddressFamily IPv4 | Where-Object { $_.DestinationPrefix -in @("192.168.10.0/24", "192.168.137.0/24", "0.0.0.0/0") } | Format-Table -AutoSize

Stop-Transcript | Out-Null
Write-Host "NDGA LAN/Hotspot repair finished. Log: $logPath"
