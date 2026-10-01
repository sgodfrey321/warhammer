"""One-time reset for the move to user accounts.

Rosters and battles gained an owning `user_id`. Existing rows predate accounts and have no
owner, so this drops every user-owned table (rosters, battles, and everything they own) and
recreates the schema fresh -- now including the ownership columns and the new User/AuthSession
tables. UnitDefinition reference data (the imported unit catalogue) is left untouched.

    cd backend && ../.venv/Scripts/python.exe -m scripts.reset_user_data

Destructive: it deletes all saved rosters and battles. Reference data survives, so no re-import
is needed afterwards.
"""

from __future__ import annotations

from sqlalchemy import text

from app import models  # noqa: F401 -- registers every table on SQLModel.metadata for create_all
from app.db import create_db_and_tables, engine

# Everything except UnitDefinition (reference data). User/AuthSession don't exist yet on an
# old DB; create_db_and_tables() below adds them. FK enforcement is off, so drop order is free.
USER_DATA_TABLES = [
    "synergyacknowledgment",
    "declaredstatepoolentry",
    "declaredstatepoolstate",
    "unitturnstate",
    "activeeffect",
    "missionscoreentry",
    "playerstate",
    "battlesession",
    "unitattachment",
    "unitsynergy",
    "declaredstatepool",
    "unit",
    "roster",
]


def main() -> int:
    with engine.begin() as conn:
        for table in USER_DATA_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
    # Recreate the dropped tables (now with user_id) plus User/AuthSession.
    create_db_and_tables()
    print(f"Reset complete: dropped {len(USER_DATA_TABLES)} user-owned tables and recreated the schema.")
    print("UnitDefinition reference data was kept. Register an account in the app to start fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
