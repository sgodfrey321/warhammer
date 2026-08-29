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
    stats: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    abilities: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    weapons: list[dict] = Field(default_factory=list, sa_column=Column(JSON))


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
    loadout: list[dict] = Field(default_factory=list, sa_column=Column(JSON))  # [{"name","count"}], import-only


class UnitSynergy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: int = Field(foreign_key="roster.id")
    source_unit_id: int = Field(foreign_key="unit.id")
    target_unit_id: int = Field(foreign_key="unit.id")
    trigger_phase: str
    note: Optional[str] = None


class UnitAttachment(SQLModel, table=True):
    """A Character attached to its bodyguard unit -- they act as one combined unit for
    movement/shooting/charging/fighting (see BattleTracker's grouped Unit Turn States).
    A led unit can have more than one leader (e.g. two characters both leading one
    squad); a leader normally leads exactly one unit, but that's not DB-enforced here."""

    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: int = Field(foreign_key="roster.id")
    leader_unit_id: int = Field(foreign_key="unit.id")
    led_unit_id: int = Field(foreign_key="unit.id")


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
    is_fights_first: bool = False  # informational tag only -- no activation-order enforcement
    flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class DeclaredStatePool(SQLModel, table=True):
    """Definition of a roster-level resource pool (Battle Focus tokens, Blessings of
    Khorne, etc.) -- roster-scoped, same tier as UnitSynergy. Not faction/indexer-derived
    (nothing upstream produces this data yet); the player declares it on their own roster."""

    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: int = Field(foreign_key="roster.id")
    name: str
    max_value: int
    scope: str  # "phase" | "turn" | "battle_round"
    stacking: bool = False


class DeclaredStatePoolState(SQLModel, table=True):
    """Runtime value for a non-stacking pool: one row per (battle, pool, owning player)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    pool_id: int = Field(foreign_key="declaredstatepool.id")
    owner_player: int
    current_value: int = 0


class DeclaredStatePoolEntry(SQLModel, table=True):
    """One accumulated instance for a stacking pool (e.g. one Blessings of Khorne roll)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    pool_id: int = Field(foreign_key="declaredstatepool.id")
    owner_player: int
    value: int
    created_at_step: int


class SynergyAcknowledgment(SQLModel, table=True):
    """Marks a UnitSynergy reminder dismissed for one specific phase instance (= one
    global_step). Reappears automatically next time that phase is entered, since a new
    instance has a different step -- no explicit reset needed."""

    id: Optional[int] = Field(default=None, primary_key=True)
    battle_session_id: int = Field(foreign_key="battlesession.id")
    synergy_id: int = Field(foreign_key="unitsynergy.id")
    step: int
