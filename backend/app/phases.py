"""Battle turn/phase progression, driven by a single monotonic step counter.

A BattleSession stores only `global_step` (incremented by one per advance-phase
call). `current_phase`, `active_player`, and `battle_round` are all derived from
it here rather than stored redundantly, so they can never drift out of sync with
each other.
"""

from __future__ import annotations

PHASE_ORDER = ["command", "movement", "shooting", "charge", "fight"]

POOL_SCOPES = {"phase", "turn", "battle_round"}

DURATION_TYPES = {
    "end_of_phase",
    "end_of_turn",
    "end_of_battle_round",
    "until_next_command_phase",
    "until_condition_clears",
    "manual",
}


def current_phase(step: int) -> str:
    return PHASE_ORDER[step % len(PHASE_ORDER)]


def active_player(step: int) -> int:
    return 1 if (step // len(PHASE_ORDER)) % 2 == 0 else 2


def battle_round(step: int) -> int:
    return step // (len(PHASE_ORDER) * 2) + 1


def transition_type(step_before_advance: int) -> str:
    """Classifies what kind of boundary is crossed by advancing past `step_before_advance`.
    Mirrors docs/battle-engine-spec.md's if/elif/else exactly, but as a pure function of
    the step rather than mutated session fields -- see phases.py's module docstring."""
    if step_before_advance % len(PHASE_ORDER) != len(PHASE_ORDER) - 1:
        return "phase_end"
    return "turn_end" if active_player(step_before_advance) == 1 else "battle_round_end"


def scopes_ending(transition: str) -> set[str]:
    """Which DeclaredStatePool scopes end (and should refill/clear) on a given transition.
    A battle-round end also ends the turn and the phase; a turn end also ends the phase."""
    scopes = {"phase"}
    if transition in ("turn_end", "battle_round_end"):
        scopes.add("turn")
    if transition == "battle_round_end":
        scopes.add("battle_round")
    return scopes


def is_expired(*, duration_type: str, owner_player: int, created_at_step: int, current_step: int) -> bool:
    """Whether an ActiveEffect should be flagged for dismissal. Never mutates
    anything -- callers surface this as a computed field, they don't auto-delete."""
    if duration_type == "end_of_phase":
        return current_step > created_at_step
    if duration_type == "end_of_turn":
        # Player-relative: only flags once *the owner's own* turn has ended, not just any
        # turn boundary. Coincides with a plain step-boundary check for the common case
        # (effect created during its own owner's turn), but matters when it isn't.
        return (
            current_step // len(PHASE_ORDER) > created_at_step // len(PHASE_ORDER)
            and active_player(created_at_step) == owner_player
        )
    if duration_type == "end_of_battle_round":
        return battle_round(current_step) > battle_round(created_at_step)
    if duration_type == "until_next_command_phase":
        return (
            current_step > created_at_step
            and current_phase(current_step) == "command"
            and active_player(current_step) == owner_player
        )
    # until_condition_clears / manual: never auto-expires.
    return False


def eligibility_warning(*, move_type: str | None, has_shot: bool, has_charged: bool) -> str | None:
    """Non-blocking warning: Advance/Fall Back normally restricts a unit's ability to
    shoot or charge that turn. Never enforced -- the player may have a mitigation the
    app doesn't know about (per app-plan's "eligibility is resolved, not hardcoded")."""
    if move_type not in ("advance", "fall_back"):
        return None
    restricted = [action for action, done in (("shoot", has_shot), ("charge", has_charged)) if done]
    if not restricted:
        return None
    verb = "Advanced" if move_type == "advance" else "Fell Back"
    return f"This unit {verb} -- it normally can't {' or '.join(restricted)} this turn."
