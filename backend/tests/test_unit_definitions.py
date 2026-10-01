from __future__ import annotations

from app.models import UnitDefinition


def _seed(session):
    session.add_all(
        [
            UnitDefinition(
                id="a",
                faction="Aeldari - Craftworlds",
                name="Asurmen",
                points_cost=95,
                keywords=["Character"],
                source_catalogue_id="cat",
                source_entry_id="a",
            ),
            UnitDefinition(
                id="b",
                faction="Aeldari - Craftworlds",
                name="Baharroth",
                points_cost=90,
                keywords=["Character"],
                source_catalogue_id="cat",
                source_entry_id="b",
            ),
            UnitDefinition(
                id="c",
                faction="Chaos - World Eaters",
                name="Khârn the Betrayer",
                points_cost=90,
                keywords=["Character"],
                source_catalogue_id="cat",
                source_entry_id="c",
            ),
        ]
    )
    session.commit()


def test_filter_by_faction(client, session):
    _seed(session)
    resp = client.get("/unit-definitions", params={"faction": "Chaos - World Eaters"})
    assert resp.status_code == 200
    names = [u["name"] for u in resp.json()]
    assert names == ["Khârn the Betrayer"]


def test_search_by_name(client, session):
    _seed(session)
    resp = client.get("/unit-definitions", params={"search": "asur"})
    assert resp.status_code == 200
    names = [u["name"] for u in resp.json()]
    assert names == ["Asurmen"]


def test_list_factions(client, session):
    _seed(session)
    resp = client.get("/unit-definitions/factions")
    assert resp.status_code == 200
    assert resp.json() == ["Aeldari - Craftworlds", "Chaos - World Eaters"]
