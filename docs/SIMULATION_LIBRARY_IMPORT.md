# NDGA Simulation Library Import (All Subjects, Offline + Online)

This flow keeps teachers URL/code-free.

- IT manager imports/curates simulation packages once.
- Teachers only see simulation cards (preview/select).
- Students run simulations from local server paths in offline mode.

Built-in NDGA practical tools now included:

- `NDGA Graph Practical Board` (offline local graph plotting)
- `NDGA Virtual Microscope Lab` (offline local biology microscope)

## 1) Seed expanded built-in catalog

```powershell
python manage.py sync_simulation_catalog --username admin@ndgakuje.org
```

This now includes broader WAEC-relevant entries across:

- Physics/Chemistry/Biology
- Mathematics
- Geography/Humanities
- Business/Commercial
- ICT/Computer
- Vocational/Home Economics/Agriculture
- NDGA local offline graph + microscope practical tools

## 2) Import all local PhET HTML5 sims at once

If PhET desktop app is installed:

```powershell
python manage.py import_local_phet --actor admin@ndgakuje.org --all --approve
```

If auto-detect fails, pass a source path:

```powershell
python manage.py import_local_phet --source "C:\path\to\simulations\html" --all --actor admin@ndgakuje.org --approve
```

## 3) Import mixed-source offline packages from manifest

Use the example manifest:

- `docs/simulations/waec_offline_manifest.json`

Run dry-run:

```powershell
python manage.py import_simulation_manifest --actor admin@ndgakuje.org --manifest-file docs/simulations/waec_offline_manifest.json --source-root C:\NDGA\simulation_sources --approve --dry-run
```

Run actual import:

```powershell
python manage.py import_simulation_manifest --actor admin@ndgakuje.org --manifest-file docs/simulations/waec_offline_manifest.json --source-root C:\NDGA\simulation_sources --approve
```

## 4) Manifest row format

Each row supports:

- `tool_name` (required)
- `tool_category` (required, one of: `SCIENCE`, `MATHEMATICS`, `ARTS`, `HUMANITIES`, `BUSINESS`, `COMPUTER_SCIENCE`)
- `source_provider` (`PHET`, `H5P`, `GEOGEBRA`, `DESMOS`, `LABXCHANGE`, `PYODIDE`, `OTHER`)
- `description`
- `local_path` (folder or zip, relative to `--source-root`)
- `entry_file` (optional HTML launch file)
- `download_url` (optional zip URL if importing from remote bundle directly)
- `online_url` (optional fallback URL)
- `score_mode` (`AUTO`, `VERIFY`, `RUBRIC`)
- `max_score`
- `scoring_callback_type` (`POST_MESSAGE`, `XAPI_STATEMENT`, `H5P_XAPI`, `PHET_WRAPPER`)
- `evidence_required`

At least one of `local_path`, `download_url`, or `online_url` must be provided.

## 5) Resulting storage path

Imported offline bundles are materialized to:

- `MEDIA_ROOT/sims/<slug>/...`

Wrappers store launch path in `offline_asset_path`, and preview runs through:

- `/cbt/simulations/launch/<wrapper_id>/`

No raw URLs or code are exposed to teachers in authoring UI.
