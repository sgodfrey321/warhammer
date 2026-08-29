from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnitDefinition(SQLModel, table=True):
    """Reference data, populated only by scripts/import_unit_definitions.py -- never
    created or edited via the API. id = the indexer's source_entry_id."""

    id: str = Field(primary_key=True)
    faction: str
    name: str
    points_cost: int = 0
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_catalogue_id: str
    source_entry_id: str
    is_legends: bool = False


class Roster(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    faction: str
    battle_size: Optional[str] = None
    points_limit: Optional[int] = None
    detachments: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Unit(SQLModel, table=True):
    """A roster entry -- one line in a Roster, referencing a UnitDefinition."""

    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: int = Field(foreign_key="roster.id")
    unit_definition_id: str = Field(foreign_key="unitdefinition.id")
    quantity: int = 1
    notes: Optional[str] = None


class UnitSynergy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: int = Field(foreign_key="roster.id")
    source_unit_id: int = Field(foreign_key="unit.id")
    target_unit_id: int = Field(foreign_key="unit.id")
    trigger_phase: str
    note: Optional[str] = None


class BattleSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=_utcnow)
    roster_id: Optional[int] = Field(default=None, foreign_key="roster.id")
    global_step: int = 0


class PlayerState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    player_number: int
    cp_gained: int = 0
    cp_spent: int = 0
    vp: int = 0


class ActiveEffect(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    label: str
    owner_player: int
    duration_type: str
    created_at_step: int
    lifts_restriction: Optional[str] = None


class UnitTurnState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    unit_id: int = Field(foreign_key="unit.id")
    battle_round: int
    turn_owner: int
    move_type: Optional[str] = None
    has_shot: bool = False
    has_charged: bool = False
    has_fought: bool = False
    flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
