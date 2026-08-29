from __future__ import annotations


def test_create_and_get_roster(client):
    resp = client.post("/rosters", json={"name": "Hank's Aeldari", "faction": "Aeldari - Craftworlds"})
    assert resp.status_code == 200
    roster = resp.json()
    assert roster["name"] == "Hank's Aeldari"

    resp = client.get(f"/rosters/{roster['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == roster["id"]


def test_update_and_delete_roster(client):
    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()

    resp = client.patch(f"/rosters/{roster['id']}", json={"points_limit": 2000})
    assert resp.status_code == 200
    assert resp.json()["points_limit"] == 2000

    resp = client.delete(f"/rosters/{roster['id']}")
    assert resp.status_code == 204
    assert client.get(f"/rosters/{roster['id']}").status_code == 404


def test_add_and_remove_unit(client, session):
    from app.models import UnitDefinition

    session.add(
        UnitDefinition(
            id="aeldari-craftworlds/asurmen",
            faction="Aeldari - Craftworlds",
            name="Asurmen",
            points_cost=95,
            keywords=["Character", "Phoenix Lord"],
            source_catalogue_id="cat",
            source_entry_id="aeldari-craftworlds/asurmen",
        )
    )
    session.commit()

    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()
    resp = client.post(
        f"/rosters/{roster['id']}/units",
        json={"unit_definition_id": "aeldari-craftworlds/asurmen", "quantity": 1},
    )
    assert resp.status_code == 200
    unit = resp.json()
    assert unit["loadout"] == []  # only BattleScribe import populates a loadout

    resp = client.patch(f"/rosters/{roster['id']}/units/{unit['id']}", json={"notes": "warlord"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "warlord"

    resp = client.delete(f"/rosters/{roster['id']}/units/{unit['id']}")
    assert resp.status_code == 204


def _seed_two_units(client, session):
    from app.models import UnitDefinition

    session.add_all(
        [
            UnitDefinition(
                id="leader", faction="Aeldari - Craftworlds", name="Jain Zar", points_cost=105,
                keywords=[], source_catalogue_id="cat", source_entry_id="leader",
            ),
            UnitDefinition(
                id="squad", faction="Aeldari - Craftworlds", name="Howling Banshees", points_cost=85,
                keywords=[], source_catalogue_id="cat", source_entry_id="squad",
            ),
        ]
    )
    session.commit()
    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()
    leader = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "leader"}).json()
    squad = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "squad"}).json()
    return roster, leader, squad


def test_manual_attachment_create_list_delete(client, session):
    roster, leader, squad = _seed_two_units(client, session)

    resp = client.post(
        f"/rosters/{roster['id']}/attachments",
        json={"leader_unit_id": leader["id"], "led_unit_id": squad["id"]},
    )
    assert resp.status_code == 200
    attachment = resp.json()

    attachments = client.get(f"/rosters/{roster['id']}/attachments").json()
    assert len(attachments) == 1
    assert attachments[0]["leader_unit_id"] == leader["id"]
    assert attachments[0]["led_unit_id"] == squad["id"]

    resp = client.delete(f"/rosters/{roster['id']}/attachments/{attachment['id']}")
    assert resp.status_code == 204
    assert client.get(f"/rosters/{roster['id']}/attachments").json() == []


def test_deleting_a_unit_cleans_up_its_attachments(client, session):
    roster, leader, squad = _seed_two_units(client, session)
    client.post(
        f"/rosters/{roster['id']}/attachments",
        json={"leader_unit_id": leader["id"], "led_unit_id": squad["id"]},
    )

    resp = client.delete(f"/rosters/{roster['id']}/units/{leader['id']}")
    assert resp.status_code == 204

    assert client.get(f"/rosters/{roster['id']}/attachments").json() == []
