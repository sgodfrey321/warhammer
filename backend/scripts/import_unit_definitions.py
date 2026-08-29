"""Upserts UnitDefinition rows from the bsdata-indexer's per-faction output JSON.

Safe to re-run after a dataslate refresh: rows are keyed by source_entry_id, so an
existing unit is updated in place rather than duplicated.

Usage: python -m scripts.import_unit_definitions [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlmodel import Session

from app.db import create_db_and_tables, engine
from app.models import UnitDefinition

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "bsdata-indexer" / "output"


def _points_cost(points: list[dict]) -> int:
    # The indexer emits a list of pricing tiers (squad size / copy number). This
    # skeleton doesn't model multi-tier pricing yet -- take the first tier as a
    # flat cost. See backend/README.md for the tradeoff.
    return points[0]["points"] if points else 0


def import_faction_file(path: Path, session: Session) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for unit in data["units"]:
        existing = session.get(UnitDefinition, unit["source_entry_id"])
        fields = dict(
            faction=unit["faction"],
            name=unit["name"],
            points_cost=_points_cost(unit.get("points", [])),
            keywords=unit.get("keywords", []),
            source_catalogue_id=unit["source_catalogue_id"],
            source_entry_id=unit["source_entry_id"],
            is_legends=unit.get("is_legends", False),
        )
        if existing is None:
            session.add(UnitDefinition(id=unit["source_entry_id"], **fields))
        else:
            for field, value in fields.items():
                setattr(existing, field, value)
            session.add(existing)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import bsdata-indexer output into UnitDefinition.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    create_db_and_tables()

    faction_files = sorted(
        p for p in args.output_dir.glob("*.json") if not p.name.endswith("-synergies.json")
    )
    if not faction_files:
        print(f"No faction output files found in {args.output_dir}")
        return 1

    with Session(engine) as session:
        total = 0
        for path in faction_files:
            n = import_faction_file(path, session)
            print(f"{path.name}: {n} units")
            total += n
        session.commit()
    print(f"Total: {total} units imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
