from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, create_engine, select

from app import db
from app.models import ActiveEffect, Unit


def test_create_db_and_tables_adds_a_missing_column_to_an_existing_table(tmp_path: Path, monkeypatch):
    """Simulates the real scenario this exists for: a database file created before
    ActiveEffect.unit_id existed. create_all() alone would leave it missing forever --
    this proves the auto-migrate step patches it in instead of 500ing on the next query."""
    scratch_path = tmp_path / "scratch.db"
    scratch_engine = create_engine(f"sqlite:///{scratch_path}")
    with scratch_engine.begin() as conn:
        # The pre-unit_id shape of ActiveEffect -- enough columns to be a real row, missing
        # only the new one.
        conn.execute(
            text(
                """
                CREATE TABLE activeeffect (
                    id INTEGER PRIMARY KEY,
                    battle_session_id INTEGER NOT NULL,
                    label VARCHAR NOT NULL,
                    owner_player INTEGER NOT NULL,
                    duration_type VARCHAR NOT NULL,
                    created_at_step INTEGER NOT NULL,
                    lifts_restriction VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO activeeffect (battle_session_id, label, owner_player, duration_type, created_at_step) "
                "VALUES (1, 'Doom', 1, 'manual', 0)"
            )
        )

    monkeypatch.setattr(db, "engine", scratch_engine)
    db.create_db_and_tables()

    columns = {col["name"] for col in inspect(scratch_engine).get_columns("activeeffect")}
    assert "unit_id" in columns

    with Session(scratch_engine) as session:
        effect = session.exec(select(ActiveEffect)).first()
        assert effect.label == "Doom"
        assert effect.unit_id is None  # pre-existing row backfills to the column's default


def test_create_db_and_tables_backfills_a_missing_json_column_to_an_empty_list(tmp_path: Path, monkeypatch):
    """The same gap, but for a non-Optional list-typed column (Unit.buffs) -- a real bug
    found live: ADD COLUMN alone leaves it NULL, which crashes UnitOut's list[dict] validation
    the first time an old row is read back. Must backfill to '[]', not just add the column."""
    scratch_path = tmp_path / "scratch.db"
    scratch_engine = create_engine(f"sqlite:///{scratch_path}")
    with scratch_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE unit (
                    id INTEGER PRIMARY KEY,
                    roster_id INTEGER NOT NULL,
                    unit_definition_id VARCHAR NOT NULL,
                    quantity INTEGER NOT NULL,
                    notes VARCHAR,
                    loadout JSON NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO unit (roster_id, unit_definition_id, quantity, loadout) "
                "VALUES (1, 'some-unit', 1, '[]')"
            )
        )

    monkeypatch.setattr(db, "engine", scratch_engine)
    db.create_db_and_tables()

    with Session(scratch_engine) as session:
        unit = session.exec(select(Unit)).first()
        assert unit.buffs == []


def test_backfill_self_heals_a_column_left_null_by_an_earlier_partial_migration(tmp_path: Path, monkeypatch):
    """The column already exists (e.g. a previous run added it before this backfill logic
    did) but is still NULL -- the real failure mode hit live. Must not skip backfilling just
    because the column is no longer "missing"."""
    scratch_path = tmp_path / "scratch.db"
    scratch_engine = create_engine(f"sqlite:///{scratch_path}")
    with scratch_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE unit (
                    id INTEGER PRIMARY KEY,
                    roster_id INTEGER NOT NULL,
                    unit_definition_id VARCHAR NOT NULL,
                    quantity INTEGER NOT NULL,
                    notes VARCHAR,
                    loadout JSON NOT NULL,
                    buffs JSON
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO unit (roster_id, unit_definition_id, quantity, loadout, buffs) "
                "VALUES (1, 'some-unit', 1, '[]', NULL)"
            )
        )

    monkeypatch.setattr(db, "engine", scratch_engine)
    db.create_db_and_tables()

    with Session(scratch_engine) as session:
        unit = session.exec(select(Unit)).first()
        assert unit.buffs == []
