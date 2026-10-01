"""Upserts UnitDefinition rows from the bsdata-indexer's per-faction output JSON.

Safe to re-run after a dataslate refresh: rows are keyed by the indexer's unique `id`, so an
existing unit is updated in place rather than duplicated. (source_entry_id is shared across
factions for some units, so it can't be the key -- older DBs keyed on it are migrated below.)

Usage: python -m scripts.import_unit_definitions [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlmodel import Session, select

from app.db import create_db_and_tables, engine
from app.models import Roster, Unit, UnitDefinition

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "bsdata-indexer" / "output"


def _points_cost(points: list[dict]) -> int:
    # points_cost stays the first tier (the base price); every tier is kept in points_tiers.
    return points[0]["points"] if points else 0


def _min_models(points: list[dict]) -> int:
    # The smallest squad size the unit is sold at (min 'models' across tiers) -- the
    # simulator uses it to default how many of each weapon are firing. 0 if unknown.
    sizes = [t["models"] for t in points if isinstance(t.get("models"), int)]
    return min(sizes) if sizes else 0


def import_faction_file(path: Path, session: Session, seen_ids: set[str] | None = None) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for unit in data["units"]:
        existing = session.get(UnitDefinition, unit["id"])
        fields = dict(
            faction=unit["faction"],
            name=unit["name"],
            points_cost=_points_cost(unit.get("points", [])),
            points_tiers=[{"models": t.get("models"), "points": t.get("points")} for t in unit.get("points", [])],
            min_models=_min_models(unit.get("points", [])),
            keywords=unit.get("keywords", []),
            role=unit.get("role"),
            source_catalogue_id=unit["source_catalogue_id"],
            source_entry_id=unit["source_entry_id"],
            is_legends=unit.get("is_legends", False),
            stats=unit.get("stats", {}),
            abilities=unit.get("abilities", []),
            rules=unit.get("rules", []),
            weapons=unit.get("weapons", []),
            model_profiles=unit.get("model_profiles", []),
        )
        if existing is None:
            session.add(UnitDefinition(id=unit["id"], **fields))
        else:
            for field, value in fields.items():
                setattr(existing, field, value)
            session.add(existing)
        if seen_ids is not None:
            seen_ids.add(unit["id"])
        count += 1
    return count


def migrate_and_prune(session: Session, current_ids: set[str]) -> tuple[int, int]:
    """Upgrades a DB built when UnitDefinition.id was source_entry_id: repoints each Unit whose
    definition id isn't a current indexer id to the current definition sharing that
    source_entry_id (preferring the roster's own faction, since several factions share some
    entries), then drops stale definitions nothing references. Returns (repointed, deleted)."""
    session.flush()
    by_source: dict[str, list[UnitDefinition]] = {}
    for d in session.exec(select(UnitDefinition)).all():
        if d.id in current_ids:
            by_source.setdefault(d.source_entry_id, []).append(d)
    factions = {r.id: (r.faction or "").casefold() for r in session.exec(select(Roster)).all()}

    repointed = 0
    for unit in session.exec(select(Unit)).all():
        if unit.unit_definition_id in current_ids:
            continue
        candidates = by_source.get(unit.unit_definition_id)
        if not candidates:
            continue
        faction = factions.get(unit.roster_id, "")
        unit.unit_definition_id = next((d for d in candidates if d.faction.casefold() == faction), candidates[0]).id
        session.add(unit)
        repointed += 1
    session.flush()

    in_use = set(session.exec(select(Unit.unit_definition_id)).all())
    deleted = 0
    for d in session.exec(select(UnitDefinition)).all():
        if d.id not in current_ids and d.id not in in_use:
            session.delete(d)
            deleted += 1
    return repointed, deleted


# Output files that exist alongside per-faction UnitDefinition JSON but aren't shaped like it
# ({"units": [...]}) -- each must be excluded here or import_faction_file crashes on it.
_NON_FACTION_FILES = {"army-rules.json", "detachments.json"}


def _faction_files(output_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in output_dir.glob("*.json")
        if not p.name.endswith("-synergies.json") and p.name not in _NON_FACTION_FILES
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import bsdata-indexer output into UnitDefinition.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    create_db_and_tables()

    faction_files = _faction_files(args.output_dir)
    if not faction_files:
        print(f"No faction output files found in {args.output_dir}")
        return 1

    with Session(engine) as session:
        total = 0
        seen_ids: set[str] = set()
        for path in faction_files:
            n = import_faction_file(path, session, seen_ids)
            print(f"{path.name}: {n} units")
            total += n
        repointed, deleted = migrate_and_prune(session, seen_ids)
        session.commit()
    if repointed or deleted:
        print(f"Migrated {repointed} roster units to new definition ids; removed {deleted} stale definitions")
    print(f"Total: {total} units imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
