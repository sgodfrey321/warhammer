from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..reference_data import REPO_ROOT, load_reference_json

router = APIRouter(prefix="/layouts", tags=["layouts"])

# Static reference data -- same pattern as army_rules.py/primary_missions.py.
# Regenerate with: python tools/gdmissions/fetch_layouts.py
OUTPUT_PATH = REPO_ROOT / "tools/gdmissions/output/layouts.json"


class LayoutOut(BaseModel):
    number: int
    name: str
    image: str
    measurements_image: str


class LayoutMatchupOut(BaseModel):
    deck: str
    vs: str
    name: str
    layouts: list[LayoutOut]


@router.get("", response_model=list[LayoutMatchupOut])
def list_layouts() -> list[dict]:
    return load_reference_json(OUTPUT_PATH)
