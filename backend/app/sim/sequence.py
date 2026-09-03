"""Resolves one weapon's full attack sequence (attacks -> hits -> wounds ->
saves -> damage -> allocation) against a defending unit's current state, per
the 2026 core rules. `resolve_sequence` is the entry point; `montecarlo.py`
calls it once per trial against a freshly-reset `DefenderState`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from .profiles import AttackerProfile, DefenderProfile

RerollPolicy = str  # "none" | "ones" | "all"


@dataclass(frozen=True)
class AttackOptions:
    """Situational toggles a player would declare before rolling, plus the
    reroll/modifier choices available to this weapon/unit combo."""

    half_range: bool = False  # for Rapid Fire / Melta
    charged: bool = False  # for Lance
    cover: bool = False
    hit_modifier: int = 0
    wound_modifier: int = 0
    reroll_hits: RerollPolicy = "none"
    reroll_wounds: RerollPolicy = "none"
    fnp: int | None = None  # the X in "Feel No Pain X+"
    anti_active: bool = False
    anti_threshold: int | None = None  # the Y in "Anti-X Y+"; only matters if anti_active


@dataclass
class DefenderState:
    """Mutable per-trial state of the defending unit: which model is
    currently taking damage and how many wounds it has left. Persists across
    every attack within one volley so no-spillover allocation works, but each
    Monte Carlo trial starts a fresh instance (see montecarlo.py)."""

    wounds_per_model: int
    model_count: int
    model_index: int = 0
    current_remaining: int = field(default=0)
    models_slain: int = 0
    damage_dealt: int = 0

    def __post_init__(self) -> None:
        if self.current_remaining == 0:
            self.current_remaining = self.wounds_per_model

    @property
    def wiped(self) -> bool:
        return self.model_index >= self.model_count

    @classmethod
    def fresh(cls, defender: DefenderProfile) -> "DefenderState":
        return cls(
            wounds_per_model=max(1, defender.wounds_per_model),
            model_count=defender.model_count,
        )


@dataclass(frozen=True)
class VolleyResult:
    damage_dealt: int
    models_slain: int


def _clamp_modifier(value: int) -> int:
    """Hit/wound modifiers are capped at +/-1 total, regardless of how many
    individual buffs/penalties stack up to that point -- a stable core rule
    (core_rules.txt, modifiers section)."""

    return max(-1, min(1, value))


def _wound_target(strength: int, toughness: int) -> int:
    """Strength-vs-Toughness -> target number needed on the wound roll."""

    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if strength * 2 <= toughness:
        return 6
    return 5


def _maybe_reroll(rng: Random, raw: int, target: int, policy: RerollPolicy) -> int:
    """Applies a reroll policy to an unmodified die result. Rerolls happen
    before modifiers are applied and a rerolled die is used as-is (no
    re-rerolling), per the task spec."""

    if policy == "ones" and raw == 1:
        return rng.randint(1, 6)
    if policy == "all" and (raw == 1 or raw < target):
        return rng.randint(1, 6)
    return raw


def _resolve_hits(attacker: AttackerProfile, options: AttackOptions, num_attacks: int, rng: Random) -> list[bool]:
    """Returns one entry per successful hit: True if that hit is guaranteed to
    wound (Lethal Hits bypassing the wound roll), False for a normal hit that
    still needs to roll to wound."""

    kw = attacker.keywords
    if kw.torrent:
        # Torrent weapons auto-hit -- no die is rolled at all, so these hits
        # can never be critical (there's no roll to crit on).
        return [False] * num_attacks

    skill = attacker.skill if attacker.skill is not None else 7  # no BS/WS -> can never hit
    hit_mod = _clamp_modifier(options.hit_modifier)

    events: list[bool] = []
    for _ in range(num_attacks):
        raw = rng.randint(1, 6)
        raw = _maybe_reroll(rng, raw, skill, options.reroll_hits)

        if raw == 1:
            continue  # unmodified 1 always fails
        if raw == 6:
            crit, success = True, True
        else:
            success = (raw + hit_mod) >= skill
            crit = False
        if not success:
            continue

        # Lethal + Devastating interaction: if a weapon has BOTH keywords,
        # auto-wounding a Lethal crit would skip the wound roll entirely and
        # so could never roll a *critical* wound -- meaning Devastating Wounds
        # could never trigger. Since rolling to wound is strictly better in
        # that case, we only take the Lethal auto-wound shortcut when
        # Devastating Wounds is NOT also present; otherwise the crit hit rolls
        # to wound normally, same as any other hit.
        guaranteed_wound = crit and kw.lethal_hits and not kw.devastating_wounds
        events.append(guaranteed_wound)

        if crit and kw.sustained_hits:
            # Extra hits generated by Sustained Hits are themselves normal
            # hits (not crits) -- they proceed to the wound roll but can't
            # trigger Lethal Hits/further Sustained Hits.
            events.extend([False] * kw.sustained_hits)

    return events


@dataclass(frozen=True)
class _WoundEvent:
    devastating: bool


def _resolve_wounds(
    attacker: AttackerProfile,
    defender: DefenderProfile,
    options: AttackOptions,
    hit_events: list[bool],
    rng: Random,
) -> list[_WoundEvent]:
    kw = attacker.keywords
    target = _wound_target(attacker.strength, defender.toughness)
    lance_bonus = 1 if (kw.lance and options.charged) else 0
    wound_mod = _clamp_modifier(options.wound_modifier + lance_bonus)
    # Twin-linked means "always re-roll failed wound rolls" -- it overrides a
    # weaker/absent reroll_wounds choice but never conflicts with "all".
    reroll_policy: RerollPolicy = "all" if kw.twin_linked else options.reroll_wounds
    anti_threshold = options.anti_threshold if options.anti_threshold is not None else kw.anti_threshold

    events: list[_WoundEvent] = []
    for guaranteed_wound in hit_events:
        if guaranteed_wound:
            # Lethal Hits auto-wound: skips the wound roll entirely, so it
            # can't be a critical wound and can't trigger Devastating Wounds
            # (see the comment in _resolve_hits for why this case only
            # happens when Devastating Wounds isn't also on the weapon).
            events.append(_WoundEvent(devastating=False))
            continue

        raw = rng.randint(1, 6)
        raw = _maybe_reroll(rng, raw, target, reroll_policy)

        if raw == 1:
            continue  # unmodified 1 always fails
        crit = raw == 6
        if not crit and options.anti_active and anti_threshold is not None and raw >= anti_threshold:
            crit = True  # Anti-X Y+: an unmodified Y+ is also a critical wound

        if crit:
            success = True
        else:
            success = (raw + wound_mod) >= target
        if not success:
            continue

        devastating = crit and kw.devastating_wounds
        events.append(_WoundEvent(devastating=devastating))

    return events


def _armour_save_needed(attacker: AttackerProfile, defender: DefenderProfile, options: AttackOptions) -> int:
    needed = defender.save - attacker.ap  # AP is stored negative, so this raises the number needed
    if options.cover and not attacker.keywords.ignores_cover:
        # +1 to the armour save. Simplified per task spec: capped so it can
        # never improve past a 2+, rather than implementing the full caveat
        # ("no cover bonus against AP 0 if already 3+ or better").
        needed = max(needed - 1, 2)
    return needed


def _save_succeeds(rng: Random, needed: int) -> bool:
    if needed > 6:
        return False  # not even a 6 would meet this target -- no valid roll
    roll = rng.randint(1, 6)
    if roll == 1:
        return False  # unmodified 1 always fails a save roll too
    return roll >= needed


def _allocate_damage(state: DefenderState, total_points: int, fnp: int | None, rng: Random) -> None:
    """Applies `total_points` of damage from a single unsaved/devastating
    wound to the defender's current model. Feel No Pain is rolled per point
    about to be lost. CRITICAL RULE: once the current model's wounds hit
    zero, any remaining points from THIS SAME attack are lost -- damage never
    spills over onto the next model. The next attack (next call) starts on
    whichever model is now current."""

    if state.wiped:
        return

    for _ in range(total_points):
        if fnp is not None:
            fnp_roll = rng.randint(1, 6)
            if fnp_roll >= fnp:
                continue  # this point of damage is felt-no-pain'd away entirely

        state.current_remaining -= 1
        state.damage_dealt += 1

        if state.current_remaining <= 0:
            state.models_slain += 1
            state.model_index += 1
            if state.wiped:
                return
            state.current_remaining = state.wounds_per_model
            break  # no spillover: the rest of this attack's damage is wasted


def resolve_into_state(
    attacker: AttackerProfile,
    defender: DefenderProfile,
    options: AttackOptions,
    state: DefenderState,
    rng: Random,
) -> None:
    """Resolves one weapon's full volley of A attacks INTO an existing
    DefenderState, mutating it in place. Firing several identical weapons (a
    whole squad's worth) at one unit within a single trial is just this called
    once per weapon against the SAME state -- so damage accumulates and the
    no-spillover allocation carries across the unit's whole shooting (see
    montecarlo.simulate's weapon_count)."""

    kw = attacker.keywords

    # 1. Number of attacks.
    num_attacks = attacker.attacks.roll(rng)
    if kw.rapid_fire and options.half_range:
        num_attacks += kw.rapid_fire
    if kw.blast:
        num_attacks += defender.model_count // 5

    # 2. Hit rolls.
    hit_events = _resolve_hits(attacker, options, num_attacks, rng)

    # 3. Wound rolls.
    wound_events = _resolve_wounds(attacker, defender, options, hit_events, rng)

    # 4 & 5. Saves + damage allocation.
    armour_needed = _armour_save_needed(attacker, defender, options)
    invuln_needed = defender.invuln
    melta_bonus = kw.melta if (kw.melta and options.half_range) else 0

    for wound in wound_events:
        if state.wiped:
            break

        if wound.devastating:
            unsaved = True  # Devastating Wounds bypasses the save step entirely
        else:
            # Defender uses whichever save (armour or invulnerable) needs the
            # lower roll -- i.e. gives the better chance of success.
            candidates = [armour_needed]
            if invuln_needed is not None:
                candidates.append(invuln_needed)
            needed = min(candidates)
            unsaved = not _save_succeeds(rng, needed)

        if not unsaved:
            continue

        damage = attacker.damage.roll(rng) + melta_bonus
        _allocate_damage(state, damage, options.fnp, rng)


def resolve_sequence(
    attacker: AttackerProfile,
    defender: DefenderProfile,
    options: AttackOptions,
    rng: Random,
) -> VolleyResult:
    """Resolves one weapon's full volley of A attacks against a FRESH unit and
    returns the damage dealt / models slain. Thin wrapper over
    resolve_into_state for the single-weapon case (and existing tests)."""

    state = DefenderState.fresh(defender)
    resolve_into_state(attacker, defender, options, state, rng)
    return VolleyResult(damage_dealt=state.damage_dealt, models_slain=state.models_slain)
