from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/secondary-missions", tags=["secondary-missions"])

# Static reference data -- same pattern as army_rules.py/primary_missions.py.
# Regenerate with: python tools/gdmissions/fetch_secondary_missions.py
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "tools" / "gdmissions" / "output" / "secondary-missions.json"
)


class ActionRowOut(BaseModel):
    k: str
    v: str


class ActionOut(BaseModel):
    title: str
    rows: list[ActionRowOut]


class SecondaryRowOut(BaseModel):
    text: str
    vp: str
    or_: bool


class SecondarySectionOut(BaseModel):
    when: str
    trigger: Optional[str]
    rows: list[SecondaryRowOut]


class SecondaryMissionOut(BaseModel):
    name: str
    slug: str
    when_drawn: Optional[str]
    action: Optional[ActionOut]
    sections: list[SecondarySectionOut]


@router.get("", response_model=list[SecondaryMissionOut])
def list_secondary_missions() -> list[dict]:
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
