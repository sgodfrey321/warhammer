"""Shared loader for the static reference JSON (indexer / gdmissions output) that the
mission, layout, army-rule and detachment routers serve straight off disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_reference_json(relative_path: str | Path) -> list:
    """Reads a repo-relative JSON file; a missing file is an empty list (generator not run yet,
    not an error). An absolute path is used as-is (Path join semantics), which lets tests
    point a router's OUTPUT_PATH at a tmp file."""
    path = REPO_ROOT / relative_path
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def find_mission(missions: list[dict], deck: str, vs: str) -> Optional[dict]:
    """Missions are keyed by the asymmetric (own deck, opposing deck) pair."""
    return next((m for m in missions if m["deck"] == deck and m["vs"] == vs), None)
