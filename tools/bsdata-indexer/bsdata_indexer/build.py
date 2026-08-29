from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import catalogue, faction_map, mfm
from .fetch import RepoCache
from .models import UnitDefinition
from .util import normalize_name, slugify

BSDATA_ORG = "BSData"
CATALOGUE_REPO = "wh40k-11e"
MFM_REPO = "wh40k-11e-mfm"


@dataclass
class BuildReport:
    faction: str
    units: list[UnitDefinition] = field(default_factory=list)
    unresolved_entrylinks: list[str] = field(default_factory=list)
    mfm_slug: str | None = None
    mfm_slug_guessed: bool = False


def build_library_index(catalogue_cache: RepoCache) -> dict[str, dict]:
    """Fetch + merge every shared library once, reused across all factions in a run."""
    return catalogue.build_global_library_index(
        lambda stem: catalogue.load_json(catalogue_cache.get(f"{stem}.json"))
    )


def build_faction(
    faction_stem: str,
    catalogue_cache: RepoCache,
    library_index: dict[str, dict],
    mfm_cache: RepoCache,
    *,
    available_mfm_slugs: set[str],
) -> BuildReport:
    faction_doc = catalogue.load_json(catalogue_cache.get(f"{faction_stem}.json"))
    resolved_entries = catalogue.resolve_faction(faction_doc, library_index)

    report = BuildReport(faction=faction_stem)
    slug, guessed = faction_map.resolve(faction_stem, available_mfm_slugs)
    report.mfm_slug = slug
    report.mfm_slug_guessed = guessed

    mfm_index: dict[str, mfm.MfmUnit] = {}
    if slug:
        mfm_doc = mfm.load_yaml(mfm_cache.get(f"data/{slug}.yaml"))
        mfm_index = mfm.index_units(mfm_doc)

    for entry in resolved_entries:
        if not entry.resolved:
            report.unresolved_entrylinks.append(entry.name)
            continue
        # The catalogue marks Legends units with a "[Legends]" name suffix; MFM instead has a
        # structured `legends` flag on the un-suffixed name, so strip it before the MFM lookup.
        base_name = entry.name
        if base_name.rstrip().endswith("[Legends]"):
            base_name = base_name.rsplit("[Legends]", 1)[0].strip()
        mfm_unit = mfm_index.get(normalize_name(base_name)) or mfm_index.get(normalize_name(entry.name))
        is_legends = (mfm_unit.is_legends if mfm_unit else False) or base_name != entry.name
        report.units.append(
            UnitDefinition(
                id=f"{slugify(faction_stem)}/{slugify(entry.name)}",
                faction=faction_stem,
                name=entry.name,
                keywords=entry.keywords,
                is_legends=is_legends,
                stats=entry.stats,
                abilities=entry.abilities,
                points=list(mfm_unit.points) if mfm_unit else [],
                mfm_matched=mfm_unit is not None,
                source_catalogue_id=entry.entrylink_id,
                source_entry_id=entry.target_id,
            )
        )
    return report


def emit(report: BuildReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{slugify(report.faction)}.json"
    payload = {
        "faction": report.faction,
        "mfm_slug": report.mfm_slug,
        "mfm_slug_guessed": report.mfm_slug_guessed,
        "unresolved_entrylinks": sorted(report.unresolved_entrylinks),
        "units": [asdict(u) for u in sorted(report.units, key=lambda u: u.name)],
    }
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path
