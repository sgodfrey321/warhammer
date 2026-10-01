from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..reference_data import REPO_ROOT, load_reference_json

router = APIRouter(prefix="/secondary-missions", tags=["secondary-missions"])

# Static reference data -- same pattern as army_rules.py/primary_missions.py.
# Regenerate with: python tools/gdmissions/fetch_secondary_missions.py
OUTPUT_PATH = REPO_ROOT / "tools/gdmissions/output/secondary-missions.json"


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
    return load_reference_json(OUTPUT_PATH)
