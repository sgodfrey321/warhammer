"""Battle turn/phase progression, driven by a single monotonic step counter.

A BattleSession stores only `global_step` (incremented by one per advance-phase
call). `current_phase`, `active_player`, and `battle_round` are all derived from
it here rather than stored redundantly, so they can never drift out of sync with
each other.
"""

from __future__ import annotations

PHASE_ORDER = ["command", "movement", "shooting", "charge", "fight"]

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


def is_expired(*, duration_type: str, owner_player: int, created_at_step: int, current_step: int) -> bool:
    """Whether an ActiveEffect should be flagged for dismissal. Never mutates
    anything -- callers surface this as a computed field, they don't auto-delete."""
    if duration_type == "end_of_phase":
        return current_step > created_at_step
    if duration_type == "end_of_turn":
        return current_step // len(PHASE_ORDER) > created_at_step // len(PHASE_ORDER)
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
