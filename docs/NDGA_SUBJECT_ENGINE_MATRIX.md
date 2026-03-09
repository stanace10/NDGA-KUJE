# NDGA Subject Engine Matrix

NDGA simulation delivery follows a fixed separation:

- `Curriculum Subject` = what is taught (Biology, Physics, Maths, Home Economics, etc.)
- `Simulation Engine` = how practical/interactive work is delivered and scored

## Core Engines

- `PhET` for science-style practical simulations
- `GeoGebra` (and Desmos where needed) for mathematics interactive tasks
- `H5P` for labeling, humanities, languages, business, vocational, and multimedia interactives

## Subject-to-Engine Defaults

| Subject Group | Preferred Engines | Typical NDGA CBT Simulation Tasks |
| --- | --- | --- |
| Biology / Health | PhET, LabXchange, H5P | Labeling organs/cells, virtual practicals, ecosystems/genetics |
| Chemistry | PhET, H5P | Equation balancing, acid/base, molecular structure activities |
| Physics / Tech Electricity | PhET, H5P | Circuits, motion/waves, troubleshooting practicals |
| Mathematics / Further Math | GeoGebra, Desmos, H5P | Graphing, geometry construction, algebra interactives |
| Computer / ICT | Pyodide/Skulpt, H5P | Coding sandbox, hardware/software labeling, process sequencing |
| Business / Commercial | H5P | Ledger/journal practicals, scenario-based tasks, matching |
| Arts / Vocational / Home Econ | H5P | Hotspots, drag/drop, interactive video, rubric practical evidence |
| Humanities / Languages | H5P | Timelines, listening drills, scenario tasks, structured writing prep |

## NDGA Implementation Rules

- Teachers pick simulations from NDGA library; they do not code integrations.
- Dean approval remains mandatory before simulation usage in live CBT.
- Auto-score callbacks use `postMessage`/xAPI payloads and write directly to CBT attempt records.
- Simulation scores can be imported to `CA3/CA4/Objective/Theory` based on writeback mapping.
- Offline/LAN mode uses local assets where available via `offline_asset_path`.
