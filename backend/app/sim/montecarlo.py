"""Monte Carlo driver: runs `resolve_sequence` many times, each against a
freshly-reset defending unit, and summarises the resulting damage/kills into a
probability distribution."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from random import Random

from .profiles import AttackerProfile, DefenderProfile
from .sequence import AttackOptions, DefenderState, resolve_into_state

DEFAULT_TRIALS = 10_000
_PERCENTILES = (10, 50, 90)
# Fractions of the target's total wounds to report "P(>= this much damage in one round)" at,
# so the summary reads "odds of stripping a quarter / half / etc. of the target this round".
_THRESHOLD_FRACTIONS = (0.25, 0.5, 0.75, 1.0)
# A game of 40k is 5 battle rounds, so that's the horizon that matters: the rounds-to-destroy
# loop stops here, and a target not dead by round 5 is one you can't reliably kill in a game
# (reported as median "> 5" / cumulative that never reaches certainty).
BATTLE_ROUNDS = 5


@dataclass(frozen=True)
class SimulationResult:
    trials: int
    weapon_count: int  # how many copies of the weapon fired per trial
    total_wounds: int  # the target unit's whole wound pool (W * model_count)
    mean_damage: float
    median_damage: float
    damage_percentiles: dict[int, float]  # e.g. {10: ..., 50: ..., 90: ...}
    damage_histogram: dict[int, int]  # wounds dealt -> count of trials
    # wounds threshold X -> P(one round deals >= X wounds). Keyed at fractions of total_wounds
    # (quarter/half/three-quarters/all), so you can read "odds I strip half of him this round".
    damage_at_least: dict[int, float]
    mean_models_slain: float
    models_slain_histogram: dict[int, int]  # models_slain -> count of trials
    p_at_least_one_kill: float
    p_wipe: float
    # Rounds-to-destroy, damage persisting between rounds (wounds don't heal): round N ->
    # cumulative P(target destroyed by end of round N). Read off your confidence level.
    destroyed_by_round: dict[int, float]
    median_rounds_to_destroy: int | None  # smallest N with cumulative P >= 0.5, or None if never within cap
    # Mean wounds / models each attacking group actually removed within the combined attack (in
    # firing order, so the parts sum to the total). Empty for the single-group wrappers.
    per_group_damage: list[float]
    per_group_slain: list[float]
    # total wounds dealt -> summed per-group contribution across trials at that total (for the
    # stacked-by-unit Wounds Dealt chart).
    damage_stack: dict[int, list[int]]


def _percentile(sorted_values: list[int], pct: int) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    # Nearest-rank on a 0-indexed list; clamped so pct=100 doesn't overflow.
    index = min(n - 1, max(0, round((pct / 100) * (n - 1))))
    return float(sorted_values[index])


# One firing line: a weapon profile and how many copies of it fire (e.g. 4 Fusion guns, plus a
# separate line for the Exarch's different gun).
WeaponLine = tuple[AttackerProfile, int]
# One attacking unit: its weapon lines plus the AttackOptions that apply to ITS attacks (its own
# abilities/re-rolls/modifiers). Several groups (e.g. Fire Dragons + a Fire Prism) can fire into
# one target, each keeping its own options -- so one unit's re-roll aura doesn't leak onto another.
WeaponGroup = tuple[list[WeaponLine], AttackOptions]


def _fire_group(weapon_lines, options, defender, state, rng) -> None:
    """Resolve one attacking unit's whole loadout into the persisting state."""
    for profile, count in weapon_lines:
        for _weapon in range(count):
            if state.wiped:
                return
            resolve_into_state(profile, defender, options, state, rng)


def _fire_round(groups: list[WeaponGroup], defender, state, rng) -> None:
    """One shooting round = every group's loadout, in order, into the persisting state."""
    for weapon_lines, options in groups:
        _fire_group(weapon_lines, options, defender, state, rng)


def _rounds_to_destroy(groups: list[WeaponGroup], defender, rng) -> int | None:
    """Repeats the whole volley round after round against ONE persisting unit
    (damage carries over -- wounds don't heal between rounds) until it's
    destroyed, returning the round it died on, or None if alive after the cap."""
    state = DefenderState.fresh(defender)
    for r in range(1, BATTLE_ROUNDS + 1):
        _fire_round(groups, defender, state, rng)
        if state.wiped:
            return r
    return None


def simulate(
    attacker: AttackerProfile,
    defender: DefenderProfile,
    options: AttackOptions,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
    weapon_count: int = 1,
) -> SimulationResult:
    """Single-weapon convenience wrapper: `weapon_count` copies of one weapon."""

    return simulate_lines([(attacker, max(1, weapon_count))], defender, options, trials=trials, seed=seed)


def simulate_lines(
    weapon_lines: list[WeaponLine],
    defender: DefenderProfile,
    options: AttackOptions,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> SimulationResult:
    """One-unit convenience wrapper: a whole (possibly mixed) loadout under one
    set of options. See `simulate_groups` for several units firing together."""

    return simulate_groups([(weapon_lines, options)], defender, trials=trials, seed=seed)


def simulate_groups(
    groups: list[WeaponGroup],
    defender: DefenderProfile,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> SimulationResult:
    """Runs `trials` independent volleys of one or more attacking units (each a
    group of weapon lines with its own options) against a fresh copy of
    `defender`'s unit each time. Every group fires into one shared DefenderState
    per trial, so damage accumulates and no-spillover allocation carries across
    the whole combined attack -- while each group keeps its own re-rolls/buffs."""

    groups = [([(p, max(1, c)) for p, c in lines], opts) for lines, opts in groups]
    total_weapons = sum(c for lines, _ in groups for _, c in lines)
    rng = Random(seed)
    total_wounds = max(1, defender.wounds_per_model * defender.model_count)

    # --- Single-round distribution (with per-group contribution) ---
    damages: list[int] = []
    slain_counts: list[int] = []
    group_damage_totals = [0] * len(groups)  # summed wounds each group actually removed, in firing order
    group_slain_totals = [0] * len(groups)
    # For the stacked histogram: per total-wounds outcome, the summed per-group contribution across
    # the trials that landed on that total (so a bar can be split by each unit's average share).
    stack_sums: dict[int, list[int]] = {}
    for _ in range(trials):
        state = DefenderState.fresh(defender)
        deltas = []
        for gi, (weapon_lines, options) in enumerate(groups):
            d0, s0 = state.damage_dealt, state.models_slain
            _fire_group(weapon_lines, options, defender, state, rng)
            dd = state.damage_dealt - d0
            deltas.append(dd)
            group_damage_totals[gi] += dd
            group_slain_totals[gi] += state.models_slain - s0
        total = state.damage_dealt
        damages.append(total)
        slain_counts.append(state.models_slain)
        bucket = stack_sums.setdefault(total, [0] * len(groups))
        for gi, dd in enumerate(deltas):
            bucket[gi] += dd

    sorted_damages = sorted(damages)

    damage_hist: dict[int, int] = {}
    for dmg in damages:
        damage_hist[dmg] = damage_hist.get(dmg, 0) + 1

    histogram: dict[int, int] = {}
    for count in slain_counts:
        histogram[count] = histogram.get(count, 0) + 1

    wipes = histogram.get(defender.model_count, 0)
    kills = trials - histogram.get(0, 0)

    # P(one round deals >= X wounds) at quarter/half/three-quarters/all of the wound pool.
    thresholds = sorted({max(1, round(f * total_wounds)) for f in _THRESHOLD_FRACTIONS})
    damage_at_least = {
        x: (sum(1 for d in damages if d >= x) / trials if trials else 0.0) for x in thresholds
    }

    # --- Rounds-to-destroy (fresh RNG stream; damage persists across rounds) ---
    rounds_rng = Random(None if seed is None else seed + 1)
    rounds_samples = [_rounds_to_destroy(groups, defender, rounds_rng) for _ in range(trials)]
    destroyed_by_round: dict[int, float] = {}
    if trials:
        for n in range(1, BATTLE_ROUNDS + 1):
            destroyed_by_round[n] = sum(1 for r in rounds_samples if r is not None and r <= n) / trials
    median_rounds = next((n for n, p in destroyed_by_round.items() if p >= 0.5), None)

    return SimulationResult(
        trials=trials,
        weapon_count=total_weapons,
        total_wounds=total_wounds,
        mean_damage=statistics.fmean(damages) if damages else 0.0,
        median_damage=statistics.median(damages) if damages else 0.0,
        damage_percentiles={p: _percentile(sorted_damages, p) for p in _PERCENTILES},
        damage_histogram=dict(sorted(damage_hist.items())),
        damage_at_least=damage_at_least,
        mean_models_slain=statistics.fmean(slain_counts) if slain_counts else 0.0,
        models_slain_histogram=dict(sorted(histogram.items())),
        p_at_least_one_kill=kills / trials if trials else 0.0,
        p_wipe=wipes / trials if trials else 0.0,
        destroyed_by_round=destroyed_by_round,
        median_rounds_to_destroy=median_rounds,
        per_group_damage=[t / trials if trials else 0.0 for t in group_damage_totals],
        per_group_slain=[t / trials if trials else 0.0 for t in group_slain_totals],
        damage_stack=dict(sorted(stack_sums.items())),
    )
