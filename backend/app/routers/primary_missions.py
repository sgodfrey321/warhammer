from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/primary-missions", tags=["primary-missions"])

# Static reference data (not roster/battle state) -- read straight from the fetcher's output,
# same pattern as army_rules.py. Regenerate with: python tools/gdmissions/fetch_missions.py
OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "gdmissions" / "output" / "primary-missions.json"


class MissionTierOut(BaseModel):
    text: str
    vp: int
    per_unit: bool
    cumulative: bool
    kind: Optional[str]


class MissionSectionOut(BaseModel):
    when: str
    trigger: Optional[str]
    header_kind: Optional[str]
    tiers: list[MissionTierOut]


class MissionOut(BaseModel):
    name: str
    deck: str
    vs: str
    # The card's "reverse" rules text, where a "(see reverse)" tier defers to it. None on the
    # many cards the upstream source doesn't carry it for.
    rule: Optional[str] = None
    sections: list[MissionSectionOut]


@router.get("", response_model=list[MissionOut])
def list_primary_missions() -> list[dict]:
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
