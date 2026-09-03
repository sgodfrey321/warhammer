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

from dataclasses import asdict

from ..sim.abilities import extract_effects
from ..sim.montecarlo import DEFAULT_TRIALS, simulate_lines
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
    single_reroll_hit: bool = False
    single_reroll_wound: bool = False
    reroll_damage: bool = False
    fnp: Optional[int] = None
    anti_active: bool = False
    anti_threshold: Optional[int] = None
    trials: int = DEFAULT_TRIALS
    seed: Optional[int] = None


class WeaponLine(BaseModel):
    # One firing line: a weapon's `characteristics` dict (A/BS-or-WS/S/AP/D/
    # Keywords/...) + its range_type (same shape as UnitDefinition.weapons[i]),
    # and how many copies fire (the A characteristic is attacks PER copy). A
    # mixed loadout is several lines -- e.g. 4 Fusion guns + 1 Exarch weapon.
    weapon_characteristics: dict[str, str] = Field(default_factory=dict)
    range_type: Literal["Ranged Weapons", "Melee Weapons"] = "Ranged Weapons"
    weapon_count: int = 1


class SimulateRequest(BaseModel):
    weapons: list[WeaponLine] = Field(default_factory=list)
    # A defender's `stats` dict (T/Sv/InSv/W/...) -- same shape as UnitDefinition.stats.
    defender_stats: dict[str, str] = Field(default_factory=dict)
    defender_model_count: int = 1
    options: SimulateOptions = Field(default_factory=SimulateOptions)


class SimulateResponse(BaseModel):
    trials: int
    weapon_count: int
    total_wounds: int
    mean_damage: float
    median_damage: float
    damage_percentiles: dict[int, float]
    damage_histogram: dict[int, int]  # wounds dealt -> count of trials
    damage_at_least: dict[int, float]  # wounds threshold -> P(one round deals >= it)
    mean_models_slain: float
    models_slain_histogram: dict[int, int]
    p_at_least_one_kill: float
    p_wipe: float
    destroyed_by_round: dict[int, float]  # round N -> cumulative P(destroyed by end of N)
    median_rounds_to_destroy: Optional[int]


class AnalyzeAbility(BaseModel):
    name: str = ""
    text: str = ""


class AnalyzeRequest(BaseModel):
    # Same shape as UnitDefinition.abilities[i] ({name, text}); the frontend
    # already holds these for the selected unit, so it just forwards them.
    abilities: list[AnalyzeAbility] = Field(default_factory=list)


class DetectedEffectOut(BaseModel):
    ability_name: str
    summary: str
    condition: str
    side: Literal["attacker", "defender"]
    option_patch: dict
    requires_target_keywords: list[str] = []


class AnalyzeResponse(BaseModel):
    effects: list[DetectedEffectOut]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_abilities(body: AnalyzeRequest) -> AnalyzeResponse:
    """Best-effort scan of a unit's abilities for attack-sequence modifiers the
    UI can offer as conditional toggles. Heuristic, not authoritative -- the UI
    still shows the raw ability text and keeps the manual controls."""

    effects = extract_effects([{"name": a.name, "text": a.text} for a in body.abilities])
    return AnalyzeResponse(effects=[DetectedEffectOut(**asdict(e)) for e in effects])


@router.post("", response_model=SimulateResponse)
def run_simulation(body: SimulateRequest) -> SimulateResponse:
    weapon_lines = [
        (
            AttackerProfile.from_characteristics(
                {"characteristics": line.weapon_characteristics, "range_type": line.range_type}
            ),
            line.weapon_count,
        )
        for line in body.weapons
    ]
    defender = DefenderProfile.from_stats(body.defender_stats, body.defender_model_count)
    options = AttackOptions(
        half_range=body.options.half_range,
        charged=body.options.charged,
        cover=body.options.cover,
        hit_modifier=body.options.hit_modifier,
        wound_modifier=body.options.wound_modifier,
        reroll_hits=body.options.reroll_hits,
        reroll_wounds=body.options.reroll_wounds,
        single_reroll_hit=body.options.single_reroll_hit,
        single_reroll_wound=body.options.single_reroll_wound,
        reroll_damage=body.options.reroll_damage,
        fnp=body.options.fnp,
        anti_active=body.options.anti_active,
        anti_threshold=body.options.anti_threshold,
    )

    logger.info(
        "SIMULATE %s vs %s [T%s Sv%s InSv%s W%s x%d models] | opts=%s trials=%d",
        [f"{line.weapon_characteristics.get('name', '?')} x{line.weapon_count} ({line.range_type})" for line in body.weapons],
        body.defender_stats.get("name", ""),
        body.defender_stats.get("T"),
        body.defender_stats.get("Sv"),
        body.defender_stats.get("InSv"),
        body.defender_stats.get("W"),
        body.defender_model_count,
        body.options.model_dump(),
        body.options.trials,
    )

    result = simulate_lines(
        weapon_lines,
        defender,
        options,
        trials=body.options.trials,
        seed=body.options.seed,
    )

    logger.info(
        "  -> mean_dmg=%.2f median=%.1f p10/50/90=%s | of %d W: P(>=X)=%s | median_rounds=%s by_round=%s",
        result.mean_damage,
        result.median_damage,
        result.damage_percentiles,
        result.total_wounds,
        {k: round(v, 3) for k, v in result.damage_at_least.items()},
        result.median_rounds_to_destroy,
        {k: round(v, 3) for k, v in result.destroyed_by_round.items()},
    )

    return SimulateResponse(
        trials=result.trials,
        weapon_count=result.weapon_count,
        total_wounds=result.total_wounds,
        mean_damage=result.mean_damage,
        median_damage=result.median_damage,
        damage_percentiles=result.damage_percentiles,
        damage_histogram=result.damage_histogram,
        damage_at_least=result.damage_at_least,
        mean_models_slain=result.mean_models_slain,
        models_slain_histogram=result.models_slain_histogram,
        p_at_least_one_kill=result.p_at_least_one_kill,
        p_wipe=result.p_wipe,
        destroyed_by_round=result.destroyed_by_round,
        median_rounds_to_destroy=result.median_rounds_to_destroy,
    )
