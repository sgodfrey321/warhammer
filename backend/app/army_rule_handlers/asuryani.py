"""Battle Focus -- the Aeldari army rule for Army Faction Asuryani (Craftworlds): a fixed
number of tokens granted at the start of each battle round based on battle size, spent on
Agile Manoeuvre triggers, unspent tokens lost at end of round. An exact fit for
DeclaredStatePool's existing non-stacking / "battle_round" scope, which advance-phase already
refills to max automatically at the right boundary -- no new state machinery needed, just the
pool created with the right numbers."""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import DeclaredStatePool, Roster

_BATTLE_FOCUS_TOKENS = {"Incursion": 2, "Strike Force": 4, "Onslaught": 6}


def _battle_focus_max(battle_size: str | None) -> int | None:
    if not battle_size:
        return None
    for label, tokens in _BATTLE_FOCUS_TOKENS.items():
        if label in battle_size:
            return tokens
    return None  # unrecognized battle_size string -- don't guess, leave it to manual add


def bootstrap(roster: Roster, session: Session) -> None:
    max_value = _battle_focus_max(roster.battle_size)
    if max_value is None:
        return
    existing = session.exec(
        select(DeclaredStatePool).where(
            DeclaredStatePool.roster_id == roster.id,
            DeclaredStatePool.name == "Battle Focus",
        )
    ).first()
    if existing is not None:
        return  # don't clobber a pool the player may have already added/edited by hand
    session.add(
        DeclaredStatePool(
            roster_id=roster.id,
            name="Battle Focus",
            max_value=max_value,
            scope="battle_round",
            stacking=False,
        )
    )
