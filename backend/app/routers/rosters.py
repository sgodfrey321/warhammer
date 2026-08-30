from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import battlescribe_import, phases
from ..army_rule_handlers import bootstrap_army_rules
from ..db import get_session
from ..models import (
    ActiveEffect,
    BattleSession,
    DeclaredStatePool,
    DeclaredStatePoolEntry,
    DeclaredStatePoolState,
    PlayerState,
    Roster,
    SynergyAcknowledgment,
    Unit,
    UnitAttachment,
    UnitDefinition,
    UnitSynergy,
    UnitTurnState,
)

router = APIRouter(prefix="/rosters", tags=["rosters"])


class UnitOut(BaseModel):
    id: int
    roster_id: int
    unit_definition_id: str
    quantity: int
    notes: Optional[str]
    loadout: list[dict]
    model_groups: list[dict]
    buffs: list[dict]
    unit_definition: UnitDefinition


class RosterCreate(BaseModel):
    name: str
    faction: str
    battle_size: Optional[str] = None
    points_limit: Optional[int] = None
    detachments: list[dict] = []


class RosterUpdate(BaseModel):
    name: Optional[str] = None
    faction: Optional[str] = None
    battle_size: Optional[str] = None
    points_limit: Optional[int] = None
    detachments: Optional[list[dict]] = None


class UnitCreate(BaseModel):
    unit_definition_id: str
    quantity: int = 1
    notes: Optional[str] = None


class UnitUpdate(BaseModel):
    quantity: Optional[int] = None
    notes: Optional[str] = None
    buffs: Optional[list[dict]] = None


class SynergyCreate(BaseModel):
    source_unit_id: int
    target_unit_id: int
    trigger_phase: str
    note: Optional[str] = None


class PoolCreate(BaseModel):
    name: str
    max_value: int
    scope: str
    stacking: bool = False


class AttachmentCreate(BaseModel):
    leader_unit_id: int
    led_unit_id: int


class RosterImportResult(BaseModel):
    roster: Roster
    imported: list[str]
    unmatched: list[str]
    attachments_created: int


def _get_roster_or_404(roster_id: int, session: Session) -> Roster:
    roster = session.get(Roster, roster_id)
    if roster is None:
        raise HTTPException(status_code=404, detail="Roster not found")
    return roster


@router.get("", response_model=list[Roster])
def list_rosters(session: Session = Depends(get_session)):
    return session.exec(select(Roster)).all()


@router.post("", response_model=Roster)
def create_roster(payload: RosterCreate, session: Session = Depends(get_session)):
    roster = Roster(**payload.model_dump())
    session.add(roster)
    session.commit()
    session.refresh(roster)
    return roster


@router.post("/import", response_model=RosterImportResult)
def import_roster(payload: dict[str, Any], session: Session = Depends(get_session)):
    """Imports a BattleScribe/NewRecruit roster export JSON, creating a Roster and
    matching each unit selection against already-imported UnitDefinitions by id
    (see app/battlescribe_import.py). Units that don't match (e.g. a faction whose
    indexer output hasn't been imported yet) are skipped, not silently dropped --
    the unmatched list is returned so the caller can see the gap."""
    parsed = battlescribe_import.parse_roster(payload)

    resolved: list[tuple[battlescribe_import.ParsedEntry, UnitDefinition]] = []
    unmatched: list[str] = []
    for entry in parsed.entries:
        definition = session.get(UnitDefinition, entry.unit_definition_id)
        if definition is None:
            unmatched.append(entry.name)
        else:
            resolved.append((entry, definition))

    faction = (
        Counter(d.faction for _, d in resolved).most_common(1)[0][0]
        if resolved
        else (parsed.faction_hint or "Unknown")
    )

    roster = Roster(
        name=parsed.name,
        faction=faction,
        battle_size=parsed.battle_size,
        points_limit=parsed.points_limit,
        detachments=parsed.detachments,
    )
    session.add(roster)
    session.commit()
    session.refresh(roster)

    imported: list[str] = []
    unit_id_by_selection: dict[str, int] = {}
    for entry, definition in resolved:
        unit = Unit(
            roster_id=roster.id,
            unit_definition_id=definition.id,
            quantity=1,
            loadout=entry.loadout,
            model_groups=entry.model_groups,
        )
        session.add(unit)
        session.flush()  # assigns unit.id without a full commit/attribute-expire
        unit_id_by_selection[entry.roster_selection_id] = unit.id
        imported.append(definition.name)

    attachments_created = 0
    for leader_sel_id, led_sel_id in parsed.attachments:
        leader_unit_id = unit_id_by_selection.get(leader_sel_id)
        led_unit_id = unit_id_by_selection.get(led_sel_id)
        if leader_unit_id is not None and led_unit_id is not None:
            session.add(UnitAttachment(roster_id=roster.id, leader_unit_id=leader_unit_id, led_unit_id=led_unit_id))
            attachments_created += 1

    session.commit()
    session.refresh(roster)  # the commits above expired roster's attributes -- reload before serializing

    bootstrap_army_rules(roster, [definition for _, definition in resolved], session)
    session.commit()
    session.refresh(roster)  # re-expired by the commit above -- reload before serializing

    return RosterImportResult(
        roster=roster, imported=imported, unmatched=unmatched, attachments_created=attachments_created
    )


@router.get("/{roster_id}", response_model=Roster)
def get_roster(roster_id: int, session: Session = Depends(get_session)):
    return _get_roster_or_404(roster_id, session)


@router.patch("/{roster_id}", response_model=Roster)
def update_roster(roster_id: int, payload: RosterUpdate, session: Session = Depends(get_session)):
    roster = _get_roster_or_404(roster_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(roster, field, value)
    roster.updated_at = datetime.now(timezone.utc)
    session.add(roster)
    session.commit()
    session.refresh(roster)
    return roster


@router.delete("/{roster_id}", status_code=204)
def delete_roster(roster_id: int, session: Session = Depends(get_session)):
    """Cascades by hand -- db.py never turns on SQLite foreign-key enforcement, so without
    this every unit/attachment/synergy/pool, and every battle (and everything a battle owns:
    player state, effects, turn states, pool runtime state, synergy acknowledgments) would be
    silently orphaned forever instead of erroring or being cleaned up."""
    roster = _get_roster_or_404(roster_id, session)

    battle_ids = [
        b.id for b in session.exec(select(BattleSession).where(BattleSession.roster_id == roster_id)).all()
    ]
    if battle_ids:
        for model in (
            PlayerState,
            ActiveEffect,
            UnitTurnState,
            DeclaredStatePoolState,
            DeclaredStatePoolEntry,
            SynergyAcknowledgment,
        ):
            for row in session.exec(select(model).where(model.battle_session_id.in_(battle_ids))).all():
                session.delete(row)
        for battle in session.exec(select(BattleSession).where(BattleSession.roster_id == roster_id)).all():
            session.delete(battle)

    for model in (UnitAttachment, UnitSynergy, DeclaredStatePool, Unit):
        for row in session.exec(select(model).where(model.roster_id == roster_id)).all():
            session.delete(row)

    session.delete(roster)
    session.commit()


def _to_unit_out(unit: Unit, session: Session) -> UnitOut:
    definition = session.get(UnitDefinition, unit.unit_definition_id)
    return UnitOut(
        id=unit.id,
        roster_id=unit.roster_id,
        unit_definition_id=unit.unit_definition_id,
        quantity=unit.quantity,
        notes=unit.notes,
        loadout=unit.loadout,
        model_groups=unit.model_groups,
        buffs=unit.buffs,
        unit_definition=definition,
    )


@router.get("/{roster_id}/units", response_model=list[UnitOut])
def list_units(roster_id: int, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    units = session.exec(select(Unit).where(Unit.roster_id == roster_id)).all()
    return [_to_unit_out(u, session) for u in units]


@router.post("/{roster_id}/units", response_model=UnitOut)
def add_unit(roster_id: int, payload: UnitCreate, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    unit = Unit(roster_id=roster_id, **payload.model_dump())
    session.add(unit)
    session.commit()
    session.refresh(unit)
    return _to_unit_out(unit, session)


@router.patch("/{roster_id}/units/{unit_id}", response_model=UnitOut)
def update_unit(roster_id: int, unit_id: int, payload: UnitUpdate, session: Session = Depends(get_session)):
    unit = session.get(Unit, unit_id)
    if unit is None or unit.roster_id != roster_id:
        raise HTTPException(status_code=404, detail="Unit not found on this roster")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)
    session.add(unit)
    session.commit()
    session.refresh(unit)
    return _to_unit_out(unit, session)


@router.delete("/{roster_id}/units/{unit_id}", status_code=204)
def delete_unit(roster_id: int, unit_id: int, session: Session = Depends(get_session)):
    unit = session.get(Unit, unit_id)
    if unit is None or unit.roster_id != roster_id:
        raise HTTPException(status_code=404, detail="Unit not found on this roster")
    for attachment in session.exec(
        select(UnitAttachment).where(
            UnitAttachment.roster_id == roster_id,
            (UnitAttachment.leader_unit_id == unit_id) | (UnitAttachment.led_unit_id == unit_id),
        )
    ).all():
        session.delete(attachment)
    session.delete(unit)
    session.commit()


@router.get("/{roster_id}/synergies", response_model=list[UnitSynergy])
def list_synergies(roster_id: int, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    return session.exec(select(UnitSynergy).where(UnitSynergy.roster_id == roster_id)).all()


@router.post("/{roster_id}/synergies", response_model=UnitSynergy)
def add_synergy(roster_id: int, payload: SynergyCreate, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    synergy = UnitSynergy(roster_id=roster_id, **payload.model_dump())
    session.add(synergy)
    session.commit()
    session.refresh(synergy)
    return synergy


@router.delete("/{roster_id}/synergies/{synergy_id}", status_code=204)
def delete_synergy(roster_id: int, synergy_id: int, session: Session = Depends(get_session)):
    synergy = session.get(UnitSynergy, synergy_id)
    if synergy is None or synergy.roster_id != roster_id:
        raise HTTPException(status_code=404, detail="Synergy not found on this roster")
    session.delete(synergy)
    session.commit()


@router.get("/{roster_id}/attachments", response_model=list[UnitAttachment])
def list_attachments(roster_id: int, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    return session.exec(select(UnitAttachment).where(UnitAttachment.roster_id == roster_id)).all()


@router.post("/{roster_id}/attachments", response_model=UnitAttachment)
def add_attachment(roster_id: int, payload: AttachmentCreate, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    attachment = UnitAttachment(roster_id=roster_id, **payload.model_dump())
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


@router.delete("/{roster_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(roster_id: int, attachment_id: int, session: Session = Depends(get_session)):
    attachment = session.get(UnitAttachment, attachment_id)
    if attachment is None or attachment.roster_id != roster_id:
        raise HTTPException(status_code=404, detail="Attachment not found on this roster")
    session.delete(attachment)
    session.commit()


@router.get("/{roster_id}/pools", response_model=list[DeclaredStatePool])
def list_pools(roster_id: int, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    return session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == roster_id)).all()


@router.post("/{roster_id}/pools", response_model=DeclaredStatePool)
def add_pool(roster_id: int, payload: PoolCreate, session: Session = Depends(get_session)):
    _get_roster_or_404(roster_id, session)
    if payload.scope not in phases.POOL_SCOPES:
        raise HTTPException(status_code=422, detail=f"Unknown scope: {payload.scope}")
    pool = DeclaredStatePool(roster_id=roster_id, **payload.model_dump())
    session.add(pool)
    session.commit()
    session.refresh(pool)
    return pool


@router.delete("/{roster_id}/pools/{pool_id}", status_code=204)
def delete_pool(roster_id: int, pool_id: int, session: Session = Depends(get_session)):
    pool = session.get(DeclaredStatePool, pool_id)
    if pool is None or pool.roster_id != roster_id:
        raise HTTPException(status_code=404, detail="Pool not found on this roster")
    session.delete(pool)
    session.commit()
