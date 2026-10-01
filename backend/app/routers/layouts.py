from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/layouts", tags=["layouts"])

# Static reference data -- same pattern as army_rules.py/primary_missions.py.
# Regenerate with: python tools/gdmissions/fetch_layouts.py
OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "gdmissions" / "output" / "layouts.json"


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
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
