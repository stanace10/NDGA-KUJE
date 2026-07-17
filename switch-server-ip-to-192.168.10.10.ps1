$ErrorActionPreference = "Stop"

$adapter = "Ethernet"
$targetIp = "192.168.10.10"
$prefixLength = 24
$gateway = "192.168.10.1"
$dnsServers = @("192.168.10.1")

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Run this script as Administrator." -ForegroundColor Red
    exit 1
}

$adapterState = Get-NetAdapter -Name $adapter -ErrorAction Stop
if ($adapterState.Status -ne "Up") {
    Write-Host "Adapter '$adapter' is not up. Check the network cable first." -ForegroundColor Red
    exit 1
}

if (Test-Connection -ComputerName $targetIp -Count 2 -Quiet) {
    Write-Host "$targetIp is still being used by another device. Turn off/change that device first, then run again." -ForegroundColor Red
    exit 1
}

Write-Host "Switching $adapter to static IP $targetIp ..." -ForegroundColor Cyan

Set-NetIPInterface -InterfaceAlias $adapter -Dhcp Disabled

Get-NetIPAddress -InterfaceAlias $adapter -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Remove-NetIPAddress -Confirm:$false

Get-NetRoute -InterfaceAlias $adapter -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
    Remove-NetRoute -Confirm:$false

New-NetIPAddress -InterfaceAlias $adapter -IPAddress $targetIp -PrefixLength $prefixLength -DefaultGateway $gateway | Out-Null
Set-DnsClientServerAddress -InterfaceAlias $adapter -ServerAddresses $dnsServers
ipconfig /flushdns | Out-Null

Write-Host "Done. This server should now answer at https://$targetIp/" -ForegroundColor Green
Get-NetIPAddress -InterfaceAlias $adapter -AddressFamily IPv4 | Format-Table InterfaceAlias,IPAddress,PrefixLength
