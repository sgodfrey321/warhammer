from __future__ import annotations

from dataclasses import dataclass

import yaml

from .models import PointsTier
from .util import normalize_name


@dataclass
class MfmUnit:
    name: str
    is_legends: bool
    points: list[PointsTier]


def load_yaml(raw: bytes) -> dict:
    return yaml.safe_load(raw)


def index_units(mfm_doc: dict) -> dict[str, MfmUnit]:
    """normalize_name(unit name) -> MfmUnit, for one faction's MFM yaml (e.g. data/aeldari.yaml).
    Keyed by normalized name, not the raw MFM string -- see util.normalize_name for why."""
    index: dict[str, MfmUnit] = {}
    for unit in mfm_doc.get("units") or []:
        tiers: list[PointsTier] = []
        for tier in unit.get("pricing") or []:
            for cost in tier.get("costs") or []:
                tiers.append(
                    PointsTier(
                        range=tier.get("range", ""),
                        models=cost.get("models", 0),
                        points=cost.get("points", 0),
                        label=tier.get("label"),
                    )
                )
        index[normalize_name(unit["name"])] = MfmUnit(
            name=unit["name"],
            is_legends=bool(unit.get("legends", False)),
            points=tiers,
        )
    return index
