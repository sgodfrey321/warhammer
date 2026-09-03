from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/detachments", tags=["detachments"])

# Static reference data (not roster/battle state) -- read straight from the indexer's output,
# same as ArmyRules. Regenerate with: python -m bsdata_indexer.cli --detachments
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "tools" / "bsdata-indexer" / "output" / "detachments.json"
)


class DetachmentRuleOut(BaseModel):
    name: str
    text: str


class DetachmentOut(BaseModel):
    name: str
    rules: list[DetachmentRuleOut]


class FactionDetachmentsOut(BaseModel):
    faction: str
    detachments: list[DetachmentOut]


@router.get("", response_model=list[FactionDetachmentsOut])
def list_detachments() -> list[dict]:
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
