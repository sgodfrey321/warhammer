"""POST /simulate -- runs the Monte Carlo dice-roll simulator (backend/app/sim)
for one weapon profile vs one defender unit and returns the resulting damage/
kill distribution. Stateless: takes raw characteristic/stat dicts in the
request body (the same shapes UnitDefinition.weapons[i].characteristics and
UnitDefinition.stats already use), not DB ids -- callers look those up first."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..sim.montecarlo import DEFAULT_TRIALS, simulate
from ..sim.profiles import AttackerProfile, DefenderProfile
from ..sim.sequence import AttackOptions

logger = logging.getLogger("app.simulate")

router = APIRouter(prefix="/simulate", tags=["simulate"])

RerollChoice = Literal["none", "ones", "all"]


class SimulateOptions(BaseModel):
    half_range: bool = False
    charged: bool = False
    cover: bool = False
    hit_modifier: int = 0
    wound_modifier: int = 0
    reroll_hits: RerollChoice = "none"
    reroll_wounds: RerollChoice = "none"
    fnp: Optional[int] = None
    anti_active: bool = False
    anti_threshold: Optional[int] = None
    trials: int = DEFAULT_TRIALS
    seed: Optional[int] = None


class SimulateRequest(BaseModel):
    # A weapon's `characteristics` dict (A/BS-or-WS/S/AP/D/Keywords/...), plus
    # which range_type it is -- same shape as UnitDefinition.weapons[i].
    weapon_characteristics: dict[str, str] = Field(default_factory=dict)
    range_type: Literal["Ranged Weapons", "Melee Weapons"] = "Ranged Weapons"
    # A defender's `stats` dict (T/Sv/InSv/W/...) -- same shape as UnitDefinition.stats.
    defender_stats: dict[str, str] = Field(default_factory=dict)
    defender_model_count: int = 1
    # How many copies of this weapon fire at the unit each trial -- e.g. a
    # 5-model squad all firing the same gun is weapon_count=5. The weapon's own
    # A characteristic is the attacks PER copy.
    weapon_count: int = 1
    options: SimulateOptions = Field(default_factory=SimulateOptions)


class SimulateResponse(BaseModel):
    trials: int
    weapon_count: int
    mean_damage: float
    median_damage: float
    damage_percentiles: dict[int, float]
    damage_histogram: dict[int, int]  # wounds dealt -> count of trials
    mean_models_slain: float
    models_slain_histogram: dict[int, int]
    p_at_least_one_kill: float
    p_wipe: float


@router.post("", response_model=SimulateResponse)
def run_simulation(body: SimulateRequest) -> SimulateResponse:
    attacker = AttackerProfile.from_characteristics(
        {"characteristics": body.weapon_characteristics, "range_type": body.range_type}
    )
    defender = DefenderProfile.from_stats(body.defender_stats, body.defender_model_count)
    options = AttackOptions(
        half_range=body.options.half_range,
        charged=body.options.charged,
        cover=body.options.cover,
        hit_modifier=body.options.hit_modifier,
        wound_modifier=body.options.wound_modifier,
        reroll_hits=body.options.reroll_hits,
        reroll_wounds=body.options.reroll_wounds,
        fnp=body.options.fnp,
        anti_active=body.options.anti_active,
        anti_threshold=body.options.anti_threshold,
    )

    logger.info(
        "SIMULATE %s (%dx, %s) vs %s [T%s Sv%s InSv%s W%s x%d models] | opts=%s trials=%d",
        body.weapon_characteristics.get("name", body.weapon_characteristics),
        body.weapon_count,
        body.range_type,
        body.defender_stats.get("name", ""),
        body.defender_stats.get("T"),
        body.defender_stats.get("Sv"),
        body.defender_stats.get("InSv"),
        body.defender_stats.get("W"),
        body.defender_model_count,
        body.options.model_dump(),
        body.options.trials,
    )

    result = simulate(
        attacker,
        defender,
        options,
        trials=body.options.trials,
        seed=body.options.seed,
        weapon_count=body.weapon_count,
    )

    logger.info(
        "  -> mean_dmg=%.2f median=%.1f p10/50/90=%s | mean_slain=%.3f P(kill)=%.3f P(wipe)=%.3f",
        result.mean_damage,
        result.median_damage,
        result.damage_percentiles,
        result.mean_models_slain,
        result.p_at_least_one_kill,
        result.p_wipe,
    )

    return SimulateResponse(
        trials=result.trials,
        weapon_count=result.weapon_count,
        mean_damage=result.mean_damage,
        median_damage=result.median_damage,
        damage_percentiles=result.damage_percentiles,
        damage_histogram=result.damage_histogram,
        mean_models_slain=result.mean_models_slain,
        models_slain_histogram=result.models_slain_histogram,
        p_at_least_one_kill=result.p_at_least_one_kill,
        p_wipe=result.p_wipe,
    )
