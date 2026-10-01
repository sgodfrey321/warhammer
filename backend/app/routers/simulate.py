"""POST /simulate -- runs the Monte Carlo dice-roll simulator (backend/app/sim)
for one weapon profile vs one defender unit and returns the resulting damage/
kill distribution. Stateless: takes raw characteristic/stat dicts in the
request body (the same shapes UnitDefinition.weapons[i].characteristics and
UnitDefinition.stats already use), not DB ids -- callers look those up first."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dataclasses import asdict

from ..sim.dice import parse_dice
from ..sim.abilities import extract_effects
from ..sim.montecarlo import DEFAULT_TRIALS, simulate_groups
from ..sim.profiles import AttackerProfile, DefenderProfile
from ..sim.sequence import AttackOptions

logger = logging.getLogger("app.simulate")

router = APIRouter(prefix="/simulate", tags=["simulate"])

RerollChoice = Literal["none", "ones", "all"]


class SimulateOptions(BaseModel):
    half_range: bool = False
    charged: bool = False
    cover: bool = False
    hit_modifier: int = Field(default=0, ge=-3, le=3)
    wound_modifier: int = Field(default=0, ge=-3, le=3)
    reroll_hits: RerollChoice = "none"
    reroll_wounds: RerollChoice = "none"
    single_reroll_hit: bool = False
    single_reroll_wound: bool = False
    reroll_damage: bool = False
    grant_sustained_hits: int = 0
    grant_lethal_hits: bool = False
    grant_devastating_wounds: bool = False
    fnp: Optional[int] = None
    anti_active: bool = False
    anti_threshold: Optional[int] = None
    damage_reduction: int = Field(default=0, ge=0, le=3)
    halve_damage: bool = False
    stationary: bool = False
    not_visible: bool = False
    trials: int = Field(default=DEFAULT_TRIALS, ge=1, le=100_000)
    seed: Optional[int] = None


class WeaponLine(BaseModel):
    # One firing line: a weapon's `characteristics` dict (A/BS-or-WS/S/AP/D/
    # Keywords/...) + its range_type (same shape as UnitDefinition.weapons[i]),
    # and how many copies fire (the A characteristic is attacks PER copy). A
    # mixed loadout is several lines -- e.g. 4 Fusion guns + 1 Exarch weapon.
    weapon_characteristics: dict[str, str] = Field(default_factory=dict)
    range_type: Literal["Ranged Weapons", "Melee Weapons"] = "Ranged Weapons"
    weapon_count: int = Field(default=1, ge=1, le=200)


class AttackerGroup(BaseModel):
    # One attacking unit: its weapon lines plus the options that apply to ITS attacks (its own
    # abilities/re-rolls/modifiers, plus the shared defender-side cover/FNP the caller repeats).
    weapons: list[WeaponLine] = Field(default_factory=list, max_length=20)
    options: SimulateOptions = Field(default_factory=SimulateOptions)


class SimulateRequest(BaseModel):
    # One or more attacking units firing into the same defender (e.g. Fire Dragons + a Fire Prism).
    attackers: list[AttackerGroup] = Field(default_factory=list, max_length=10)
    # A defender's `stats` dict (T/Sv/InSv/W/...) -- same shape as UnitDefinition.stats.
    defender_stats: dict[str, str] = Field(default_factory=dict)
    defender_model_count: int = Field(default=1, ge=1, le=200)
    # The defender's keywords (e.g. ["Vehicle", "Monster"]); lets Anti-X on weapons auto-apply.
    defender_keywords: list[str] = Field(default_factory=list, max_length=50)


class PerUnitOut(BaseModel):
    mean_damage: float
    mean_models_slain: float


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
    per_unit: list[PerUnitOut]  # per attacking unit, in the order sent
    damage_stack: dict[int, list[int]]  # total wounds -> summed per-unit contribution (for the stacked chart)


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


def _attack_options(o: SimulateOptions) -> AttackOptions:
    return AttackOptions(
        half_range=o.half_range,
        charged=o.charged,
        cover=o.cover,
        hit_modifier=o.hit_modifier,
        wound_modifier=o.wound_modifier,
        reroll_hits=o.reroll_hits,
        reroll_wounds=o.reroll_wounds,
        single_reroll_hit=o.single_reroll_hit,
        single_reroll_wound=o.single_reroll_wound,
        reroll_damage=o.reroll_damage,
        grant_sustained_hits=o.grant_sustained_hits,
        grant_lethal_hits=o.grant_lethal_hits,
        grant_devastating_wounds=o.grant_devastating_wounds,
        fnp=o.fnp,
        anti_active=o.anti_active,
        anti_threshold=o.anti_threshold,
        damage_reduction=o.damage_reduction,
        halve_damage=o.halve_damage,
        stationary=o.stationary,
        not_visible=o.not_visible,
    )


@router.post("", response_model=SimulateResponse)
def run_simulation(body: SimulateRequest) -> SimulateResponse:
    for group in body.attackers:
        for line in group.weapons:
            for key in ("A", "D"):
                try:
                    parse_dice(line.weapon_characteristics.get(key))
                except ValueError:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Unparseable dice notation for {key}: {line.weapon_characteristics.get(key)!r}",
                    )
    groups = [
        (
            [
                (
                    AttackerProfile.from_characteristics(
                        {"characteristics": line.weapon_characteristics, "range_type": line.range_type}
                    ),
                    line.weapon_count,
                )
                for line in group.weapons
            ],
            _attack_options(group.options),
        )
        for group in body.attackers
    ]
    defender = DefenderProfile.from_stats(body.defender_stats, body.defender_model_count, body.defender_keywords)
    # trials/seed are sim-level; the frontend keeps them consistent across units, so read the first.
    first_opts = body.attackers[0].options if body.attackers else SimulateOptions()

    logger.info(
        "SIMULATE %s vs %s [T%s Sv%s InSv%s W%s x%d models] trials=%d",
        [
            [f"{line.weapon_characteristics.get('name', '?')} x{line.weapon_count}" for line in group.weapons]
            for group in body.attackers
        ],
        body.defender_stats.get("name", ""),
        body.defender_stats.get("T"),
        body.defender_stats.get("Sv"),
        body.defender_stats.get("InSv"),
        body.defender_stats.get("W"),
        body.defender_model_count,
        first_opts.trials,
    )

    result = simulate_groups(
        groups,
        defender,
        trials=first_opts.trials,
        seed=first_opts.seed,
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
        per_unit=[
            PerUnitOut(mean_damage=d, mean_models_slain=s)
            for d, s in zip(result.per_group_damage, result.per_group_slain)
        ],
        damage_stack=result.damage_stack,
    )
