from __future__ import annotations

from pathlib import Path

from scripts.import_unit_definitions import import_faction_file
from app.models import UnitDefinition
from sqlmodel import select

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "bsdata-indexer" / "output"
AELDARI_FILE = OUTPUT_DIR / "aeldari-craftworlds.json"


def test_import_real_aeldari_output(session):
    assert AELDARI_FILE.exists(), "expected the committed indexer output fixture to exist"

    count = import_faction_file(AELDARI_FILE, session)
    session.commit()
    assert count > 0

    rows = session.exec(select(UnitDefinition)).all()
    assert len(rows) == count

    asurmen = session.exec(select(UnitDefinition).where(UnitDefinition.name == "Asurmen")).first()
    assert asurmen is not None
    assert asurmen.points_cost > 0
    assert "Phoenix Lord" in asurmen.keywords
    assert asurmen.stats.get("M") == '7"'
    assert any(a["name"] == "Hand of Asuryan" for a in asurmen.abilities)

    # A squad unit -- stats resolved via the nested-model fallback (catalogue.py), not
    # present directly on the squad's own entry.
    dire_avengers = session.exec(select(UnitDefinition).where(UnitDefinition.name == "Dire Avengers")).first()
    assert dire_avengers is not None
    assert dire_avengers.stats.get("M") is not None

    # Catalogue config entries (Detachment, Battle Focus rule) must not import as units.
    assert session.exec(select(UnitDefinition).where(UnitDefinition.name == "Detachment")).first() is None


def test_import_is_idempotent(session):
    import_faction_file(AELDARI_FILE, session)
    session.commit()
    first_count = len(session.exec(select(UnitDefinition)).all())

    import_faction_file(AELDARI_FILE, session)
    session.commit()
    second_count = len(session.exec(select(UnitDefinition)).all())

    assert first_count == second_count
