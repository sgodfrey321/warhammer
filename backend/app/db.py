from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import JSON, inspect, text
from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "warhammer.db"
# WARHAMMER_DB_PATH overrides the default -- lets throwaway/test runs (or a second local
# instance) use an isolated file instead of the one holding real roster/battle data.
DB_PATH = Path(os.environ["WARHAMMER_DB_PATH"]) if os.environ.get("WARHAMMER_DB_PATH") else DEFAULT_DB_PATH
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def _add_missing_columns() -> None:
    """No migration tooling in this project -- create_all() only ever creates missing
    *tables*, never adds columns to ones that already exist. So a model gaining a new field
    (e.g. ActiveEffect.unit_id) would silently 500 against any database file created before
    that change, forever, until someone thought to migrate it by hand. Diff each table's
    columns against SQLModel's metadata and patch the gap instead.

    A freshly added column is NULL on every pre-existing row, which is fine for an Optional
    field but breaks one typed as a plain (non-Optional) list/dict, e.g. Unit.buffs --
    default_factory=list only ever applies to newly-constructed Python objects, never
    backfills existing DB rows. Every JSON column in this codebase (loadout, buffs, keywords,
    abilities, weapons, detachments, flags) is list-shaped, so backfill those specifically to
    '[]' rather than leaving them NULL. SQLite's ADD COLUMN still rejects a NOT NULL addition
    with no default on a non-empty table, which is the right failure mode (loud, not silent)
    for anything this doesn't cover.

    The backfill runs unconditionally on every startup, not just the run that adds the column
    -- a database that already picked up the column as NULL (e.g. from a run of this function
    before this backfill existed) needs to self-heal too, not stay broken forever just because
    the column technically exists now."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column.type.compile(engine.dialect)}'
                    conn.execute(text(ddl))
                if isinstance(column.type, JSON):
                    conn.execute(
                        text(f'UPDATE "{table.name}" SET "{column.name}" = \'[]\' WHERE "{column.name}" IS NULL')
                    )


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
