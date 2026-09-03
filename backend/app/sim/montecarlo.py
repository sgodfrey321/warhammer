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


def _percentile(sorted_values: list[int], pct: int) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    # Nearest-rank on a 0-indexed list; clamped so pct=100 doesn't overflow.
    index = min(n - 1, max(0, round((pct / 100) * (n - 1))))
    return float(sorted_values[index])


# One firing line: a weapon profile and how many copies of it fire (e.g. 4 Fusion guns, plus a
# separate line for the Exarch's different gun). All lines fire into one shared DefenderState.
WeaponLine = tuple[AttackerProfile, int]


def _one_round(weapon_lines: list[WeaponLine], defender, options, state, rng) -> None:
    """One shooting round = every copy of every weapon line resolved into the persisting state."""
    for profile, count in weapon_lines:
        for _weapon in range(count):
            if state.wiped:
                return
            resolve_into_state(profile, defender, options, state, rng)


def _rounds_to_destroy(weapon_lines: list[WeaponLine], defender, options, rng) -> int | None:
    """Repeats the whole volley round after round against ONE persisting unit
    (damage carries over -- wounds don't heal between rounds) until it's
    destroyed, returning the round it died on, or None if alive after the cap."""
    state = DefenderState.fresh(defender)
    for r in range(1, BATTLE_ROUNDS + 1):
        _one_round(weapon_lines, defender, options, state, rng)
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
    """Single-weapon convenience wrapper: `weapon_count` copies of one weapon.
    See `simulate_lines` for a mixed loadout (e.g. a squad's guns plus a
    differently-armed Exarch)."""

    return simulate_lines([(attacker, max(1, weapon_count))], defender, options, trials=trials, seed=seed)


def simulate_lines(
    weapon_lines: list[WeaponLine],
    defender: DefenderProfile,
    options: AttackOptions,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> SimulationResult:
    """Runs `trials` independent volleys of a whole (possibly mixed) loadout
    against a fresh copy of `defender`'s unit each time, returning the resulting
    distribution of wounds dealt / models slain. Every weapon line fires into
    one shared DefenderState per trial, so damage accumulates and allocation
    (with no spillover) carries across the unit's whole shooting."""

    weapon_lines = [(p, max(1, c)) for p, c in weapon_lines] or []
    total_weapons = sum(c for _, c in weapon_lines)
    rng = Random(seed)
    total_wounds = max(1, defender.wounds_per_model * defender.model_count)

    # --- Single-round distribution ---
    damages: list[int] = []
    slain_counts: list[int] = []
    for _ in range(trials):
        state = DefenderState.fresh(defender)
        _one_round(weapon_lines, defender, options, state, rng)
        damages.append(state.damage_dealt)
        slain_counts.append(state.models_slain)

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
    rounds_samples = [_rounds_to_destroy(weapon_lines, defender, options, rounds_rng) for _ in range(trials)]
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
    )
