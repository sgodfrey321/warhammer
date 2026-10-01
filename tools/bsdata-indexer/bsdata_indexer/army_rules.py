"""Extracts catalogue/library-level army rules (Battle Focus, Blessings of Khorne, etc.) --
distinct from per-unit abilities in catalogue.py. These live in a catalogue's own top-level
`rules` (library catalogues) or `sharedRules` (non-library catalogues, e.g. World Eaters
carries its own Blessings of Khorne directly) rather than on any unit entry, so they need
their own pass over every cached catalogue file rather than the per-faction unit walk in
build.py. Reuses the Ability dataclass (name + text) -- same shape, no need for a new one."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .catalogue import load_json
from .fetch import RepoCache
from .models import Ability


def extract_army_rules(doc: dict) -> list[Ability]:
    # Repo file listings aren't limited to catalogues -- the game system file ("Warhammer
    # 40,000.json") carries a top-level "gameSystem" key instead of "catalogue" and has no
    # army rules of the kind this module cares about, so skip it rather than assume every
    # listed file is catalogue-shaped.
    cat = doc.get("catalogue")
    if cat is None:
        return []
    raw = (cat.get("rules") or []) + (cat.get("sharedRules") or [])
    return [Ability(name=r["name"], text=(r.get("description") or "").strip()) for r in raw if r.get("name")]


def build_all(catalogue_cache: RepoCache) -> list[dict]:
    """One entry per cached catalogue file that carries its own rules/sharedRules -- most
    faction files (e.g. Aeldari - Craftworlds) have none of their own, since their army rules
    live in a separate shared library file they link to (Aeldari - Aeldari Library)."""
    stems = sorted(n[:-5] for n in catalogue_cache.list_files() if n.endswith(".json"))
    factions = []
    for stem in stems:
        doc = load_json(catalogue_cache.get(f"{stem}.json"))
        rules = extract_army_rules(doc)
        if not rules:
            continue
        factions.append(
            {
                "faction": doc["catalogue"].get("name", stem),
                "rules": [asdict(r) for r in rules],
            }
        )
    return factions


def emit(factions: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "army-rules.json"
    out_path.write_text(json.dumps(factions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
