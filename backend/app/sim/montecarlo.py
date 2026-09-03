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


@dataclass(frozen=True)
class SimulationResult:
    trials: int
    weapon_count: int  # how many copies of the weapon fired per trial
    mean_damage: float
    median_damage: float
    damage_percentiles: dict[int, float]  # e.g. {10: ..., 50: ..., 90: ...}
    damage_histogram: dict[int, int]  # wounds dealt -> count of trials
    mean_models_slain: float
    models_slain_histogram: dict[int, int]  # models_slain -> count of trials
    p_at_least_one_kill: float
    p_wipe: float


def _percentile(sorted_values: list[int], pct: int) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    # Nearest-rank on a 0-indexed list; clamped so pct=100 doesn't overflow.
    index = min(n - 1, max(0, round((pct / 100) * (n - 1))))
    return float(sorted_values[index])


def simulate(
    attacker: AttackerProfile,
    defender: DefenderProfile,
    options: AttackOptions,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
    weapon_count: int = 1,
) -> SimulationResult:
    """Runs `trials` independent volleys against a fresh copy of `defender`'s
    unit each time, and returns the resulting distribution of wounds dealt /
    models slain. `weapon_count` is how many copies of `attacker`'s weapon fire
    at the unit each trial -- e.g. a 5-model squad all firing the same gun is
    weapon_count=5. All those weapons share one DefenderState per trial, so
    damage accumulates and allocation carries across the unit."""

    weapon_count = max(1, weapon_count)
    rng = Random(seed)

    damages: list[int] = []
    slain_counts: list[int] = []
    for _ in range(trials):
        state = DefenderState.fresh(defender)
        for _weapon in range(weapon_count):
            if state.wiped:
                break
            resolve_into_state(attacker, defender, options, state, rng)
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

    return SimulationResult(
        trials=trials,
        weapon_count=weapon_count,
        mean_damage=statistics.fmean(damages) if damages else 0.0,
        median_damage=statistics.median(damages) if damages else 0.0,
        damage_percentiles={p: _percentile(sorted_damages, p) for p in _PERCENTILES},
        damage_histogram=dict(sorted(damage_hist.items())),
        mean_models_slain=statistics.fmean(slain_counts) if slain_counts else 0.0,
        models_slain_histogram=dict(sorted(histogram.items())),
        p_at_least_one_kill=kills / trials if trials else 0.0,
        p_wipe=wipes / trials if trials else 0.0,
    )
