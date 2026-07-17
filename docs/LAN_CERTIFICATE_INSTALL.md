# NDGA LAN Certificate Install

Run this on each Windows LAN computer that will open the NDGA LAN portal.

## One-computer manual install

1. Copy or open the NDGA folder on the computer.
2. Open PowerShell.
3. Run:

```powershell
cd C:\NDGA
powershell -ExecutionPolicy Bypass -File .\scripts\install_ndga_lan_root_cert.ps1
```

The script now accepts either:

- `C:\NDGA\certs\lan\ndga-lan-root.crt`
- `C:\NDGA\certs\lan\ndga-lan.crt`

It installs the certificate into the current Windows user's trusted root store.

## If Chrome still says Not Secure

Close all Chrome/Edge windows and reopen the browser. If it still shows Not Secure:

1. Confirm the LAN address is exactly the certificate address.
2. Confirm the computer date/time is correct.
3. Re-run the script for the logged-in Windows user.
4. If many Windows users share the same PC, run the script once under each user account or import the certificate into Local Machine Trusted Root with an administrator account.

## Local Machine install for shared lab PCs

Open PowerShell as Administrator:

```powershell
$cert = "C:\NDGA\certs\lan\ndga-lan.crt"
Import-Certificate -FilePath $cert -CertStoreLocation Cert:\LocalMachine\Root
```

Restart Chrome/Edge after installation.

