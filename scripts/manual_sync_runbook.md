# Manual Sync Rule

This project now runs on manual sync only.

## Ownership

- `LAN` owns:
  - CBT runtime
  - CBT attempts
  - CBT score writeback
  - elections
- `Cloud` owns:
  - manual CA
  - theory
  - normal result entry workflow
  - student/staff/admin profile changes
  - finance

## Hard Rule

Teachers must not enter the same score component on both sides.

- CBT-owned score parts come from `LAN`
- Manual-owned score parts come from `Cloud`

## Daily Safe Flow

### 1. After CBT closes for the day

Run on the LAN machine:

```powershell
.\scripts\sync_lan_to_cloud_cbt.ps1
```

This will:

1. repair CBT writebacks locally
2. push CBT-owned rows to cloud
3. print the LAN sync queue summary

### 2. Before the next day or after manual score entry on cloud

Run on the LAN machine:

```powershell
.\scripts\sync_cloud_to_lan_results.ps1
```

This will pull only the cloud-owned result models needed for teacher score visibility on LAN.

## Optional Admin/Profile Pulls

Do **not** run broad profile or setup pulls by default.

If there is a special case like:

- new student created on cloud
- staff profile corrected on cloud
- admin account change needed on LAN

handle that as a supervised one-off pull so academic structure and stale cloud setup data do not come back.

## Goal

The queue does not need to stay empty forever.

The real goal is:

- no automatic background sync
- no double entry for the same score component
- manual batches only when requested
- queue returns clean after each manual run
