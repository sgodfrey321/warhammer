from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import UnitDefinition

router = APIRouter(prefix="/unit-definitions", tags=["unit-definitions"])


@router.get("/factions", response_model=list[str])
def list_factions(session: Session = Depends(get_session)):
    rows = session.exec(select(UnitDefinition.faction).distinct()).all()
    return sorted(rows)


@router.get("", response_model=list[UnitDefinition])
def list_unit_definitions(
    faction: Optional[str] = None,
    search: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(UnitDefinition)
    if faction:
        query = query.where(UnitDefinition.faction == faction)
    if search:
        query = query.where(UnitDefinition.name.ilike(f"%{search}%"))
    return session.exec(query).all()
