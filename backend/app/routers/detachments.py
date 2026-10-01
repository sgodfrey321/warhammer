from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..reference_data import REPO_ROOT, load_reference_json

router = APIRouter(prefix="/detachments", tags=["detachments"])

# Static reference data (not roster/battle state) -- read straight from the indexer's output,
# same as ArmyRules. Regenerate with: python -m bsdata_indexer.cli --detachments
OUTPUT_PATH = REPO_ROOT / "tools/bsdata-indexer/output/detachments.json"


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
    return load_reference_json(OUTPUT_PATH)
