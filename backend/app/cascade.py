"""Hand-rolled cascade deletes -- db.py never enables SQLite foreign-key enforcement, so every
delete path must clean up its dependents itself or they're orphaned silently. All helpers
flush nothing and commit nothing; the caller owns the transaction."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, or_, select as sa_select
from sqlmodel import Session

from .models import (
    ActiveEffect,
    BattleSession,
    DeclaredStatePool,
    DeclaredStatePoolEntry,
    DeclaredStatePoolState,
    MissionScoreEntry,
    PlayerState,
    Roster,
    SynergyAcknowledgment,
    Unit,
    UnitAttachment,
    UnitSynergy,
    UnitTurnState,
)

_BATTLE_OWNED = (
    PlayerState,
    ActiveEffect,
    UnitTurnState,
    DeclaredStatePoolState,
    DeclaredStatePoolEntry,
    SynergyAcknowledgment,
    MissionScoreEntry,
)


def delete_battles(session: Session, battle_ids: Iterable[int]) -> None:
    ids = list(battle_ids)
    if not ids:
        return
    for model in _BATTLE_OWNED:
        session.execute(delete(model).where(model.battle_session_id.in_(ids)))
    session.execute(delete(BattleSession).where(BattleSession.id.in_(ids)))


def delete_synergies(session: Session, synergy_ids: Iterable[int]) -> None:
    ids = list(synergy_ids)
    if not ids:
        return
    session.execute(delete(SynergyAcknowledgment).where(SynergyAcknowledgment.synergy_id.in_(ids)))
    session.execute(delete(UnitSynergy).where(UnitSynergy.id.in_(ids)))


def delete_pools(session: Session, pool_ids: Iterable[int]) -> None:
    ids = list(pool_ids)
    if not ids:
        return
    session.execute(delete(DeclaredStatePoolState).where(DeclaredStatePoolState.pool_id.in_(ids)))
    session.execute(delete(DeclaredStatePoolEntry).where(DeclaredStatePoolEntry.pool_id.in_(ids)))
    session.execute(delete(DeclaredStatePool).where(DeclaredStatePool.id.in_(ids)))


def delete_units(session: Session, unit_ids: Iterable[int]) -> None:
    """Also removes everything that points at these units, in this roster or any battle
    (an opponent-side unit's turn states/effects live on someone else's battle)."""
    ids = list(unit_ids)
    if not ids:
        return
    synergy_ids = session.execute(
        sa_select(UnitSynergy.id).where(or_(UnitSynergy.source_unit_id.in_(ids), UnitSynergy.target_unit_id.in_(ids)))
    ).scalars().all()
    delete_synergies(session, synergy_ids)
    session.execute(delete(ActiveEffect).where(ActiveEffect.unit_id.in_(ids)))
    session.execute(delete(UnitTurnState).where(UnitTurnState.unit_id.in_(ids)))
    session.execute(
        delete(UnitAttachment).where(or_(UnitAttachment.leader_unit_id.in_(ids), UnitAttachment.led_unit_id.in_(ids)))
    )
    session.execute(delete(Unit).where(Unit.id.in_(ids)))


def delete_roster(session: Session, roster_id: int) -> None:
    battle_ids = session.execute(sa_select(BattleSession.id).where(BattleSession.roster_id == roster_id)).scalars().all()
    delete_battles(session, battle_ids)
    # Keep battles that merely used this roster as the opponent -- just drop the dangling link.
    session.execute(
        BattleSession.__table__.update().where(BattleSession.opponent_roster_id == roster_id).values(opponent_roster_id=None)
    )
    delete_units(session, session.execute(sa_select(Unit.id).where(Unit.roster_id == roster_id)).scalars().all())
    delete_synergies(session, session.execute(sa_select(UnitSynergy.id).where(UnitSynergy.roster_id == roster_id)).scalars().all())
    session.execute(delete(UnitAttachment).where(UnitAttachment.roster_id == roster_id))
    delete_pools(session, session.execute(sa_select(DeclaredStatePool.id).where(DeclaredStatePool.roster_id == roster_id)).scalars().all())
    session.execute(delete(Roster).where(Roster.id == roster_id))
