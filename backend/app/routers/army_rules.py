from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..reference_data import REPO_ROOT, load_reference_json

router = APIRouter(prefix="/army-rules", tags=["army-rules"])

# Static reference data (not roster/battle state) -- read straight from the indexer's output,
# same as UnitDefinition's source data, but not worth a DB table + import step for a page that
# just lists it. Regenerate with: python -m bsdata_indexer.cli --army-rules
OUTPUT_PATH = REPO_ROOT / "tools/bsdata-indexer/output/army-rules.json"


class ArmyRuleOut(BaseModel):
    name: str
    text: str


class FactionArmyRulesOut(BaseModel):
    faction: str
    rules: list[ArmyRuleOut]


@router.get("", response_model=list[FactionArmyRulesOut])
def list_army_rules() -> list[dict]:
    return load_reference_json(OUTPUT_PATH)
