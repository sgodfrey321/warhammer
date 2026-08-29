from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "warhammer.db"
# WARHAMMER_DB_PATH overrides the default -- lets throwaway/test runs (or a second local
# instance) use an isolated file instead of the one holding real roster/battle data.
DB_PATH = Path(os.environ["WARHAMMER_DB_PATH"]) if os.environ.get("WARHAMMER_DB_PATH") else DEFAULT_DB_PATH
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
