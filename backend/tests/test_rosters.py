from __future__ import annotations

from sqlmodel import select

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
    assert unit["buffs"] == []

    resp = client.patch(f"/rosters/{roster['id']}/units/{unit['id']}", json={"notes": "warlord"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "warlord"

    buffs = [{"label": "Battle Focus: Fade Back", "stat": "M", "modifier": '+2"'}]
    resp = client.patch(f"/rosters/{roster['id']}/units/{unit['id']}", json={"buffs": buffs})
    assert resp.status_code == 200
    assert resp.json()["buffs"] == buffs

    units = client.get(f"/rosters/{roster['id']}/units").json()
    assert units[0]["buffs"] == buffs

    resp = client.delete(f"/rosters/{roster['id']}/units/{unit['id']}")
    assert resp.status_code == 204


def test_declare_model_groups_on_a_hand_added_unit(client, session):
    """A manually-added unit starts with model_groups == [] (only roster import populates them);
    PATCHing model_groups lets the details view build its per-model-type table."""
    from app.models import UnitDefinition

    session.add(
        UnitDefinition(
            id="aeldari-craftworlds/guardians",
            faction="Aeldari - Craftworlds",
            name="Guardian Defenders",
            points_cost=100,
            min_models=10,
            keywords=["Battleline", "Infantry"],
            source_catalogue_id="cat",
            source_entry_id="aeldari-craftworlds/guardians",
        )
    )
    session.commit()

    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()
    unit = client.post(
        f"/rosters/{roster['id']}/units",
        json={"unit_definition_id": "aeldari-craftworlds/guardians", "quantity": 1},
    ).json()
    assert unit["model_groups"] == []  # only BattleScribe import populates model_groups

    groups = [{"name": "Guardian Defenders", "count": 10}]
    resp = client.patch(f"/rosters/{roster['id']}/units/{unit['id']}", json={"model_groups": groups})
    assert resp.status_code == 200
    assert resp.json()["model_groups"] == groups

    # Persisted, not just echoed back.
    units = client.get(f"/rosters/{roster['id']}/units").json()
    assert units[0]["model_groups"] == groups


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


def test_delete_roster_cascades_everything(client, session):
    from app.models import (
        ActiveEffect,
        BattleSession,
        DeclaredStatePool,
        DeclaredStatePoolState,
        PlayerState,
        Unit,
        UnitAttachment,
        UnitSynergy,
        UnitTurnState,
    )

    roster, leader, squad = _seed_two_units(client, session)
    roster_id = roster["id"]
    client.post(
        f"/rosters/{roster_id}/attachments",
        json={"leader_unit_id": leader["id"], "led_unit_id": squad["id"]},
    )
    client.post(
        f"/rosters/{roster_id}/synergies",
        json={"source_unit_id": leader["id"], "target_unit_id": squad["id"], "trigger_phase": "command"},
    )
    pool = client.post(
        f"/rosters/{roster_id}/pools", json={"name": "Battle Focus", "max_value": 4, "scope": "battle_round"}
    ).json()

    battle = client.post("/battles", json={"roster_id": roster_id}).json()
    client.patch(f"/battles/{battle['id']}/players/1", json={"cp_gained": 1})
    client.patch(f"/battles/{battle['id']}/units/{leader['id']}/turn-state", json={"move_type": "normal"})
    client.post(f"/battles/{battle['id']}/effects", json={"label": "Doom", "owner_player": 1, "duration_type": "manual"})
    client.post(f"/battles/{battle['id']}/pools/{pool['id']}/spend", json={"amount": 1})  # populates pool state

    resp = client.delete(f"/rosters/{roster_id}")
    assert resp.status_code == 204
    assert client.get(f"/rosters/{roster_id}").status_code == 404

    assert session.exec(select(Unit).where(Unit.roster_id == roster_id)).all() == []
    assert session.exec(select(UnitAttachment).where(UnitAttachment.roster_id == roster_id)).all() == []
    assert session.exec(select(UnitSynergy).where(UnitSynergy.roster_id == roster_id)).all() == []
    assert session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == roster_id)).all() == []
    assert session.exec(select(BattleSession).where(BattleSession.roster_id == roster_id)).all() == []
    assert session.exec(select(PlayerState).where(PlayerState.battle_session_id == battle["id"])).all() == []
    assert session.exec(select(ActiveEffect).where(ActiveEffect.battle_session_id == battle["id"])).all() == []
    assert session.exec(select(UnitTurnState).where(UnitTurnState.battle_session_id == battle["id"])).all() == []
    assert (
        session.exec(select(DeclaredStatePoolState).where(DeclaredStatePoolState.battle_session_id == battle["id"])).all()
        == []
    )


def test_deleting_a_unit_cleans_up_its_attachments(client, session):
    roster, leader, squad = _seed_two_units(client, session)
    client.post(
        f"/rosters/{roster['id']}/attachments",
        json={"leader_unit_id": leader["id"], "led_unit_id": squad["id"]},
    )

    resp = client.delete(f"/rosters/{roster['id']}/units/{leader['id']}")
    assert resp.status_code == 204

    assert client.get(f"/rosters/{roster['id']}/attachments").json() == []
