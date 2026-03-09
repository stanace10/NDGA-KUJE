from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from django.core import management
from django.core.management.base import BaseCommand, CommandError

from apps.cbt.models import (
    CBTSimulationCallbackType,
    CBTSimulationScoreMode,
    CBTSimulationSourceProvider,
    CBTSimulationToolCategory,
)


PROVIDER_PHET = "PHET"
PROVIDER_CHEMCOLLECTIVE = "CHEMCOLLECTIVE"
PROVIDER_VIRTUAL_LABS = "VIRTUAL_LABS"
PROVIDER_ICT = "ICT"
PROVIDER_NDGA_CORE = "NDGA_CORE"

SUPPORTED_PROVIDER_GROUPS = {
    PROVIDER_PHET,
    PROVIDER_CHEMCOLLECTIVE,
    PROVIDER_VIRTUAL_LABS,
    PROVIDER_ICT,
    PROVIDER_NDGA_CORE,
}


@dataclass(frozen=True)
class ManifestSeedRow:
    group: str
    tool_name: str
    tool_type: str
    source_provider: str
    source_reference_url: str
    tool_category: str
    description: str
    online_url: str = ""
    entry_file: str = "index.html"
    score_mode: str = CBTSimulationScoreMode.VERIFY
    max_score: str = "10.00"
    scoring_callback_type: str = CBTSimulationCallbackType.POST_MESSAGE
    evidence_required: bool = True
    local_candidates: list[str] = field(default_factory=list)


CATALOG_SEED: tuple[ManifestSeedRow, ...] = (
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Pendulum Lab",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/pendulum-lab/latest/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Physics practical for period, oscillation, and SHM analysis.",
        online_url="https://phet.colorado.edu/sims/html/pendulum-lab/latest/pendulum-lab_en.html",
        entry_file="pendulum-lab_en.html",
        local_candidates=["phet/pendulum-lab", "phet/pendulum-lab.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Projectile Motion",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/projectile-motion/latest/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Physics practical for trajectories, vectors, and range.",
        online_url="https://phet.colorado.edu/sims/html/projectile-motion/latest/projectile-motion_en.html",
        entry_file="projectile-motion_en.html",
        local_candidates=["phet/projectile-motion", "phet/projectile-motion.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Circuit Construction Kit: DC",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/circuit-construction-kit-dc/latest/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Electric circuit practical with bulbs, current, and resistance.",
        online_url="https://phet.colorado.edu/sims/html/circuit-construction-kit-dc/latest/circuit-construction-kit-dc_en.html",
        entry_file="circuit-construction-kit-dc_en.html",
        local_candidates=[
            "phet/circuit-construction-kit-dc",
            "phet/circuit-construction-kit-dc.zip",
        ],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Concentration",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/concentration/latest/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Chemistry practical for solution concentration and dilution.",
        online_url="https://phet.colorado.edu/sims/html/concentration/latest/concentration_en.html",
        entry_file="concentration_en.html",
        local_candidates=["phet/concentration", "phet/concentration.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET pH Scale",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/ph-scale/latest/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Chemistry practical for acids, bases, and pH scale.",
        online_url="https://phet.colorado.edu/sims/html/ph-scale/latest/ph-scale_en.html",
        entry_file="ph-scale_en.html",
        local_candidates=["phet/ph-scale", "phet/ph-scale.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Area Builder",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/area-builder/latest/",
        tool_category=CBTSimulationToolCategory.MATHEMATICS,
        description="Mathematics practical for area modeling and decomposition.",
        online_url="https://phet.colorado.edu/sims/html/area-builder/latest/area-builder_en.html",
        entry_file="area-builder_en.html",
        local_candidates=["phet/area-builder", "phet/area-builder.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_PHET,
        tool_name="PhET Graphing Lines",
        tool_type="HTML5 Simulation",
        source_provider=CBTSimulationSourceProvider.PHET,
        source_reference_url="https://phet.colorado.edu/sims/html/graphing-lines/latest/",
        tool_category=CBTSimulationToolCategory.MATHEMATICS,
        description="Mathematics practical for slope, intercept, and line relations.",
        online_url="https://phet.colorado.edu/sims/html/graphing-lines/latest/graphing-lines_en.html",
        entry_file="graphing-lines_en.html",
        local_candidates=["phet/graphing-lines", "phet/graphing-lines.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_CHEMCOLLECTIVE,
        tool_name="ChemCollective Virtual Lab",
        tool_type="Virtual Lab",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://chemcollective.org/vlabs",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Virtual chemistry lab for titration, equilibrium, and molarity practicals.",
        online_url="https://chemcollective.org/vlab",
        local_candidates=[
            "chemcollective/virtual-lab",
            "chemcollective/virtual-lab.zip",
        ],
    ),
    ManifestSeedRow(
        group=PROVIDER_VIRTUAL_LABS,
        tool_name="Virtual Labs: Ohm's Law",
        tool_type="Virtual Lab",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://github.com/Virtual-Labs/exp-ohms-law-iitkgp",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Electrical practical for Ohm's law setup and interpretation.",
        online_url="https://github.com/Virtual-Labs/exp-ohms-law-iitkgp",
        local_candidates=[
            "virtual-labs/ohms-law",
            "virtual-labs/exp-ohms-law-iitkgp",
            "virtual-labs/ohms-law.zip",
        ],
    ),
    ManifestSeedRow(
        group=PROVIDER_VIRTUAL_LABS,
        tool_name="Virtual Labs: Simple Harmonic Motion",
        tool_type="Virtual Lab",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://github.com/Virtual-Labs/exp-simple-harmonic-motion",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Physics practical for SHM experiment setup and reading.",
        online_url="https://github.com/Virtual-Labs/exp-simple-harmonic-motion",
        local_candidates=[
            "virtual-labs/simple-harmonic-motion",
            "virtual-labs/exp-simple-harmonic-motion",
            "virtual-labs/simple-harmonic-motion.zip",
        ],
    ),
    ManifestSeedRow(
        group=PROVIDER_ICT,
        tool_name="Blockly Algorithm Studio",
        tool_type="Programming Sandbox",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://developers.google.com/blockly",
        tool_category=CBTSimulationToolCategory.COMPUTER_SCIENCE,
        description="ICT practical for algorithm blocks, flow logic, and task sequencing.",
        online_url="https://developers.google.com/blockly",
        score_mode=CBTSimulationScoreMode.RUBRIC,
        local_candidates=["ict/blockly-studio", "ict/blockly-studio.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_ICT,
        tool_name="GeoGebra Graphing Board",
        tool_type="Interactive Graphing",
        source_provider=CBTSimulationSourceProvider.GEOGEBRA,
        source_reference_url="https://www.geogebra.org/",
        tool_category=CBTSimulationToolCategory.MATHEMATICS,
        description="Graph practical board for coordinate plotting and function analysis.",
        online_url="https://www.geogebra.org/graphing",
        score_mode=CBTSimulationScoreMode.VERIFY,
        local_candidates=["geogebra/graphing", "geogebra/graphing.zip"],
    ),
    ManifestSeedRow(
        group=PROVIDER_NDGA_CORE,
        tool_name="NDGA Graph Practical Board",
        tool_type="Interactive Graphing",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://ndgakuje.org/",
        tool_category=CBTSimulationToolCategory.MATHEMATICS,
        description="Offline NDGA graph practical board for coordinate plotting and evidence capture.",
        online_url="",
        entry_file="index.html",
        local_candidates=[
            "static/sims/ndga-graph-practical",
            "static/sims/ndga-graph-practical.zip",
        ],
    ),
    ManifestSeedRow(
        group=PROVIDER_NDGA_CORE,
        tool_name="NDGA Virtual Microscope Lab",
        tool_type="Virtual Microscope",
        source_provider=CBTSimulationSourceProvider.OTHER,
        source_reference_url="https://ndgakuje.org/",
        tool_category=CBTSimulationToolCategory.SCIENCE,
        description="Offline NDGA virtual microscope with magnification/focus controls and evidence capture.",
        online_url="",
        entry_file="index.html",
        local_candidates=[
            "static/sims/ndga-virtual-microscope",
            "static/sims/ndga-virtual-microscope.zip",
        ],
    ),
)


def _resolve_local_path(*, source_root: Path, candidates: list[str]) -> str:
    for raw in candidates:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = source_root / candidate
        candidate = candidate.resolve()
        if candidate.exists():
            try:
                return candidate.relative_to(source_root).as_posix()
            except ValueError:
                return candidate.as_posix()
    return ""


class Command(BaseCommand):
    help = (
        "Build a mixed-source WAEC practical simulation manifest "
        "(PhET + ChemCollective + Virtual Labs + ICT packs), and optionally import in one command."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-file",
            default="docs/simulations/waec_mixed_manifest.generated.json",
            help="Manifest output file path.",
        )
        parser.add_argument(
            "--source-root",
            default=".",
            help="Base folder used to auto-detect local simulation bundles/folders.",
        )
        parser.add_argument(
            "--providers",
            default="PHET,CHEMCOLLECTIVE,VIRTUAL_LABS,ICT,NDGA_CORE",
            help="Comma-separated provider groups to include.",
        )
        parser.add_argument(
            "--import-now",
            action="store_true",
            help="Immediately import manifest into SimulationWrapper registry.",
        )
        parser.add_argument(
            "--username",
            default="",
            help="IT actor username/email used for --import-now (alias: --actor).",
        )
        parser.add_argument(
            "--actor",
            default="",
            help="IT actor username/email used for --import-now (alias for --username).",
        )
        parser.add_argument(
            "--approve",
            action="store_true",
            help="Mark imported wrappers as APPROVED during --import-now.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build manifest and run import in preview mode only.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output_file"]).resolve()
        source_root = Path(options["source_root"]).resolve()
        dry_run = bool(options["dry_run"])
        import_now = bool(options["import_now"])

        requested_groups = {
            chunk.strip().upper()
            for chunk in (options.get("providers") or "").split(",")
            if chunk.strip()
        }
        if not requested_groups:
            raise CommandError("At least one provider group is required in --providers.")
        unknown = requested_groups - SUPPORTED_PROVIDER_GROUPS
        if unknown:
            raise CommandError(
                f"Unsupported provider group(s): {', '.join(sorted(unknown))}. "
                f"Supported: {', '.join(sorted(SUPPORTED_PROVIDER_GROUPS))}"
            )

        rows = []
        local_count = 0
        online_fallback_count = 0
        skipped = 0

        for seed in CATALOG_SEED:
            if seed.group not in requested_groups:
                continue

            row = {
                "tool_name": seed.tool_name,
                "tool_type": seed.tool_type,
                "source_provider": seed.source_provider,
                "source_reference_url": seed.source_reference_url,
                "tool_category": seed.tool_category,
                "description": seed.description,
                "score_mode": seed.score_mode,
                "max_score": seed.max_score,
                "scoring_callback_type": seed.scoring_callback_type,
                "evidence_required": seed.evidence_required,
                "entry_file": seed.entry_file,
            }

            local_path = _resolve_local_path(
                source_root=source_root,
                candidates=seed.local_candidates,
            )
            if local_path:
                row["local_path"] = local_path
                local_count += 1
            elif seed.online_url:
                row["online_url"] = seed.online_url
                online_fallback_count += 1
            else:
                skipped += 1
                continue

            rows.append(row)

        if not rows:
            raise CommandError("No manifest rows could be built from the selected providers.")

        payload = {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "build_mixed_sim_manifest",
                "providers": sorted(requested_groups),
                "source_root": source_root.as_posix(),
                "counts": {
                    "rows": len(rows),
                    "local_paths": local_count,
                    "online_fallback": online_fallback_count,
                    "skipped": skipped,
                },
            },
            "rows": rows,
        }

        if not dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Manifest written: {output_path}"))
        else:
            self.stdout.write(self.style.WARNING("Dry-run enabled: manifest file not written."))

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Rows built={len(rows)} | local={local_count} | "
                    f"online_fallback={online_fallback_count} | skipped={skipped}"
                )
            )
        )

        if not import_now:
            return

        actor_key = (options.get("username") or "").strip() or (options.get("actor") or "").strip()
        if not actor_key:
            raise CommandError("Provide --username or --actor when using --import-now.")

        if dry_run:
            temp_manifest = output_path.parent / f"{output_path.stem}.dryrun.json"
            temp_manifest.parent.mkdir(parents=True, exist_ok=True)
            temp_manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            manifest_file = temp_manifest
        else:
            manifest_file = output_path

        management.call_command(
            "import_simulation_manifest",
            username=actor_key,
            manifest_file=str(manifest_file),
            source_root=str(source_root),
            approve=bool(options.get("approve")),
            dry_run=dry_run,
        )
