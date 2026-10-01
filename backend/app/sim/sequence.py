"""Resolves one weapon's full attack sequence (attacks -> hits -> wounds ->
saves -> damage -> allocation) against a defending unit's current state, per
the 2026 core rules. `resolve_sequence` is the entry point; `montecarlo.py`
calls it once per trial against a freshly-reset `DefenderState`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

from .dice import DiceNotation
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
    # "Re-roll one Hit/Wound roll" (e.g. Fire Prism's Crystal Matrix): a single
    # failed die per volley, distinct from the re-roll-all policies above.
    single_reroll_hit: bool = False
    single_reroll_wound: bool = False
    reroll_damage: bool = False  # "re-roll the Damage roll" -- re-roll a below-average variable-damage result
    # Keywords granted to the whole unit's attacks by an ability (e.g. Bladestorm -> Sustained
    # Hits 1), on top of whatever the weapon profile already has.
    grant_sustained_hits: int = 0
    grant_lethal_hits: bool = False
    grant_devastating_wounds: bool = False
    fnp: int | None = None  # the X in "Feel No Pain X+"
    anti_active: bool = False
    anti_threshold: int | None = None  # manual Y in "Anti-X Y+"; only used if anti_active (min'd with the auto-matched one)
    damage_reduction: int = 0  # "subtract N from the Damage characteristic", applied per attack, min 1
    halve_damage: bool = False  # "halve the Damage characteristic" (rounds up), applied before damage_reduction
    stationary: bool = False  # Heavy: +1 to hit if the attacker remained stationary
    not_visible: bool = False  # Indirect Fire at a non-visible target: -1 to hit and the target gets cover


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


def _effective_anti_threshold(attacker: AttackerProfile, defender: DefenderProfile, options: AttackOptions) -> int | None:
    """Lowest threshold among the weapon's Anti-X entries that match the defender's keywords,
    min'd with the manual override when `anti_active` is set."""

    have = {k.casefold() for k in defender.defender_keywords}
    best: int | None = None
    for targets, threshold in attacker.keywords.anti:
        if targets and all(t.startswith("non-") for t in targets):
            matched = not any(t[4:] in have for t in targets)
        else:
            matched = any(t in have for t in targets)
        if matched and (best is None or threshold < best):
            best = threshold
    if options.anti_active and options.anti_threshold is not None:
        best = options.anti_threshold if best is None else min(best, options.anti_threshold)
    return best


def _hit_outcome(raw: int, skill: int, modifier: int) -> tuple[bool, bool]:
    """(success, crit) for a hit die: unmodified 1 always fails, unmodified 6
    always crits (and hits); otherwise the modified roll must meet the skill."""

    if raw == 1:
        return False, False
    if raw == 6:
        return True, True
    return (raw + modifier) >= skill, False


def _wound_outcome(raw: int, target: int, modifier: int, anti_threshold: int | None) -> tuple[bool, bool]:
    """(success, crit) for a wound die. Same 1-always-fails / 6-always-crits
    rule as hits, plus Anti-X: an unmodified roll >= the anti threshold is also
    a critical wound."""

    if raw == 1:
        return False, False
    crit = raw == 6 or (anti_threshold is not None and raw >= anti_threshold)
    if crit:
        return True, True
    return (raw + modifier) >= target, False


def _roll_damage(damage: DiceNotation, reroll: bool, rng: Random) -> int:
    """Rolls damage; with `reroll` (a 're-roll the Damage roll' ability), a
    variable-damage result that comes up below its own average is re-rolled once
    and the new result kept -- the standard 're-roll a low damage roll' play.
    Flat damage has nothing to re-roll."""

    value = damage.roll(rng)
    if reroll and damage.die > 0 and value < damage.average():
        value = damage.roll(rng)
    return value


def _reroll_applies(raw: int, success: bool, policy: RerollPolicy) -> bool:
    """The re-roll waterfall for a die you're allowed to re-roll: only failures
    are ever re-rolled (never a success or crit). An unmodified 1 always counts
    as a failure, so it's always a re-roll candidate; a 're-roll failures'/all
    policy additionally re-rolls any roll that failed AFTER modifiers, while
    're-roll 1s' re-rolls only natural 1s. Each die is re-rolled at most once --
    the re-rolled result stands even if it too fails (no re-re-rolls)."""

    if success or policy == "none":
        return False
    if policy == "ones":
        return raw == 1
    return True  # "all": re-roll any failure (natural 1s included)


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
    hit_mod = _clamp_modifier(
        options.hit_modifier
        + (1 if kw.heavy and options.stationary else 0)
        - (1 if kw.indirect_fire and options.not_visible else 0)
    )

    # Effective crit-triggered keywords = the weapon's own plus any granted by an ability
    # (e.g. Bladestorm grants [Sustained Hits 1]).
    sustained = kw.sustained_hits
    lethal = kw.lethal_hits or options.grant_lethal_hits
    devastating = kw.devastating_wounds or options.grant_devastating_wounds

    def record_hit(crit: bool) -> None:
        # Lethal Hits is mandatory: a crit hit auto-wounds (no wound roll), so it is never a
        # critical wound and can't trigger Devastating Wounds even if the weapon has both.
        events.append(crit and lethal)
        if crit:
            # Sustained extra hits are themselves normal hits (not crits) -- they
            # proceed to the wound roll but can't re-trigger Lethal/Sustained.
            extra = (sustained.roll(rng) if sustained else 0) + options.grant_sustained_hits
            events.extend([False] * extra)

    events: list[bool] = []
    eligible_failures = 0  # failed dice NOT already re-rolled by policy -- candidates for the single re-roll
    for _ in range(num_attacks):
        raw = rng.randint(1, 6)
        success, crit = _hit_outcome(raw, skill, hit_mod)
        rerolled = False
        if _reroll_applies(raw, success, options.reroll_hits):
            raw = rng.randint(1, 6)
            success, crit = _hit_outcome(raw, skill, hit_mod)
            rerolled = True
        if success:
            record_hit(crit)
        elif not rerolled:
            eligible_failures += 1

    # "Re-roll one Hit roll": one failed die that wasn't already re-rolled by the
    # policy gets a single re-roll (a die can never be re-rolled twice, so if the
    # policy already re-rolled every failure this does nothing).
    if options.single_reroll_hit and eligible_failures > 0:
        raw = rng.randint(1, 6)
        success, crit = _hit_outcome(raw, skill, hit_mod)
        if success:
            record_hit(crit)

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
    anti_threshold = _effective_anti_threshold(attacker, defender, options)
    devastating = kw.devastating_wounds or options.grant_devastating_wounds  # incl. an ability-granted keyword

    events: list[_WoundEvent] = []
    eligible_failures = 0  # failed dice NOT already re-rolled by policy -- candidates for the single re-roll
    for guaranteed_wound in hit_events:
        if guaranteed_wound:
            # Lethal Hits auto-wound: skips the wound roll entirely, so it
            # can't be a critical wound and can't trigger Devastating Wounds.
            events.append(_WoundEvent(devastating=False))
            continue

        raw = rng.randint(1, 6)
        success, crit = _wound_outcome(raw, target, wound_mod, anti_threshold)
        rerolled = False
        if _reroll_applies(raw, success, reroll_policy):
            raw = rng.randint(1, 6)
            success, crit = _wound_outcome(raw, target, wound_mod, anti_threshold)
            rerolled = True
        if success:
            events.append(_WoundEvent(devastating=crit and devastating))
        elif not rerolled:
            eligible_failures += 1

    # "Re-roll one Wound roll": a single failed die not already re-rolled (see the
    # matching note in _resolve_hits).
    if options.single_reroll_wound and eligible_failures > 0:
        raw = rng.randint(1, 6)
        success, crit = _wound_outcome(raw, target, wound_mod, anti_threshold)
        if success:
            events.append(_WoundEvent(devastating=crit and devastating))

    return events


def _armour_save_needed(attacker: AttackerProfile, defender: DefenderProfile, options: AttackOptions) -> int:
    needed = defender.save - attacker.ap  # AP is stored negative, so this raises the number needed
    cover = options.cover or (attacker.keywords.indirect_fire and options.not_visible)
    if cover and not attacker.keywords.ignores_cover:
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
        num_attacks += kw.rapid_fire.roll(rng)  # rolled once per weapon volley, not per attack
    if kw.blast:
        num_attacks += defender.model_count // 5

    # 2. Hit rolls.
    hit_events = _resolve_hits(attacker, options, num_attacks, rng)

    # 3. Wound rolls.
    wound_events = _resolve_wounds(attacker, defender, options, hit_events, rng)

    # 4 & 5. Saves + damage allocation.
    armour_needed = _armour_save_needed(attacker, defender, options)
    invuln_needed = defender.invuln
    melta = kw.melta if (kw.melta and options.half_range) else None

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

        damage = _roll_damage(attacker.damage, options.reroll_damage, rng) + (melta.roll(rng) if melta else 0)
        if damage > 0:
            if options.halve_damage:
                damage = (damage + 1) // 2
            damage = max(1, damage - options.damage_reduction)  # reduction can't take an attack below 1 damage
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
