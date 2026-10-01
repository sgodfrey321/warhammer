from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from app import reference_data
from app.models import (
    ActiveEffect,
    BattleSession,
    DeclaredStatePoolEntry,
    DeclaredStatePoolState,
    MissionScoreEntry,
    Roster,
    SynergyAcknowledgment,
    Unit,
    UnitDefinition,
    UnitSynergy,
    UnitTurnState,
)
from app.routers import primary_missions
from scripts.import_unit_definitions import import_faction_file, migrate_and_prune

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "bsdata-indexer" / "output"
HANK = Path(__file__).resolve().parent.parent.parent / "docs" / "Hank 2k.json"


def _defn(session, id_, source=None, faction="F", tiers=None, cost=10, name="U"):
    session.add(
        UnitDefinition(
            id=id_, faction=faction, name=name, points_cost=cost, points_tiers=tiers or [],
            keywords=[], source_catalogue_id="cat", source_entry_id=source or id_,
        )
    )
    session.commit()


def _roster(client, faction="F"):
    return client.post("/rosters", json={"name": "R", "faction": faction}).json()


def _unit(client, roster, def_id):
    return client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": def_id}).json()


# 1. points

def test_unit_points_falls_back_to_tier_matching_model_groups(client, session):
    _defn(session, "sq", tiers=[{"models": 5, "points": 80}, {"models": 10, "points": 150}], cost=80)
    roster = _roster(client)
    unit = _unit(client, roster, "sq")
    assert unit["points"] == 80
    resp = client.patch(
        f"/rosters/{roster['id']}/units/{unit['id']}", json={"model_groups": [{"name": "A", "count": 10}]}
    )
    assert resp.json()["points"] == 150
    session.get(Unit, unit["id"]).points = 123
    session.commit()
    assert client.get(f"/rosters/{roster['id']}/units").json()[0]["points"] == 123


def test_import_records_real_points_and_tiers(client, session):
    import_faction_file(OUTPUT_DIR / "aeldari-craftworlds.json", session)
    session.commit()
    fd = session.exec(select(UnitDefinition).where(UnitDefinition.name == "Fire Dragons")).first()
    assert len(fd.points_tiers) >= 1 and fd.points_cost == fd.points_tiers[0]["points"]

    result = client.post("/rosters/import", json=json.loads(HANK.read_text(encoding="utf-8"))).json()
    units = client.get(f"/rosters/{result['roster']['id']}/units").json()
    assert sum(u["points"] for u in units) == 1990


# 2. PK collisions

def test_shared_source_entry_id_yields_one_definition_per_faction(session):
    for f in ("chaos-world-eaters", "chaos-thousand-sons", "chaos-chaos-daemons"):
        import_faction_file(OUTPUT_DIR / f"{f}.json", session)
    session.commit()
    rows = session.exec(select(UnitDefinition).where(UnitDefinition.name == "Cerberus [Legends]")).all()
    assert len({r.faction for r in rows}) == len(rows) >= 2
    assert len({r.source_entry_id for r in rows}) < len(rows)  # genuinely shared


def test_import_roster_prefers_faction_hint_for_ambiguous_source_id(client, session):
    _defn(session, "a/x", source="shared", faction="Chaos - World Eaters", name="X")
    _defn(session, "b/x", source="shared", faction="Chaos - Thousand Sons", name="X")
    payload = {
        "roster": {
            "name": "T",
            "forces": [
                {
                    "catalogueName": "chaos - thousand sons",
                    "selections": [{"type": "unit", "name": "X", "id": "s1", "entryId": "link::shared"}],
                }
            ],
        }
    }
    result = client.post("/rosters/import", json=payload).json()
    assert result["roster"]["faction"] == "Chaos - Thousand Sons"
    units = client.get(f"/rosters/{result['roster']['id']}/units").json()
    assert units[0]["unit_definition_id"] == "b/x"


def test_migration_repoints_units_and_prunes_stale_definitions(client, session):
    _defn(session, "shared", source="shared", faction="Old")  # legacy row: id == source_entry_id
    _defn(session, "orphan", source="orphan")
    _defn(session, "a/x", source="shared", faction="Chaos - World Eaters")
    _defn(session, "b/x", source="shared", faction="Chaos - Thousand Sons")
    roster = _roster(client, "Chaos - Thousand Sons")
    unit = _unit(client, roster, "shared")

    repointed, deleted = migrate_and_prune(session, {"a/x", "b/x"})
    session.commit()

    assert (repointed, deleted) == (1, 2)
    assert session.get(Unit, unit["id"]).unit_definition_id == "b/x"
    assert session.get(UnitDefinition, "shared") is None and session.get(UnitDefinition, "orphan") is None


# 3. validation

def test_add_unit_unknown_definition_is_404_and_listing_stays_healthy(client):
    roster = _roster(client)
    assert client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "nope"}).status_code == 404
    assert client.get(f"/rosters/{roster['id']}/units").status_code == 200


def test_synergy_and_attachment_validate_units(client, session):
    _defn(session, "d")
    r1, r2 = _roster(client), _roster(client)
    a, b = _unit(client, r1, "d"), _unit(client, r1, "d")
    other = _unit(client, r2, "d")
    syn = f"/rosters/{r1['id']}/synergies"
    att = f"/rosters/{r1['id']}/attachments"
    body = {"trigger_phase": "shooting"}
    assert client.post(syn, json={**body, "source_unit_id": a["id"], "target_unit_id": 999}).status_code == 404
    assert client.post(syn, json={**body, "source_unit_id": a["id"], "target_unit_id": other["id"]}).status_code == 404
    assert client.post(syn, json={**body, "source_unit_id": a["id"], "target_unit_id": b["id"]}).status_code == 200
    assert client.post(att, json={"leader_unit_id": a["id"], "led_unit_id": a["id"]}).status_code == 422
    assert client.post(att, json={"leader_unit_id": a["id"], "led_unit_id": other["id"]}).status_code == 404
    assert client.post(att, json={"leader_unit_id": a["id"], "led_unit_id": b["id"]}).status_code == 200


# 4. pool owner

def test_spend_pool_uses_owner_player_not_active_player(client):
    roster = _roster(client)
    battle = client.post("/battles", json={"roster_id": roster["id"]}).json()
    pool = client.post(
        f"/rosters/{roster['id']}/pools", json={"name": "BF", "max_value": 4, "scope": "turn"}
    ).json()
    for _ in range(5):  # into player 2's turn
        client.patch(f"/battles/{battle['id']}/advance-phase")
    url = f"/battles/{battle['id']}/pools/{pool['id']}/spend"
    out = client.post(url, json={"amount": 1}).json()
    vals = {s["owner_player"]: s["current_value"] for s in out["pool_states"]}
    assert vals[1] == 3 and vals.get(2, 4) == 4
    assert client.post(url, json={"owner_player": 3}).status_code == 422
    add = f"/battles/{battle['id']}/pools/{pool['id']}/add"
    assert client.post(add, json={"owner_player": 0, "value": 1}).status_code == 422


# 5. setup change

def test_changing_disposition_clears_scores_and_vp(client, session, monkeypatch, tmp_path):
    payload = [
        {"name": "M", "deck": d, "vs": v, "sections": [{"when": "", "trigger": None, "header_kind": None,
         "tiers": [{"text": "t", "vp": 5, "per_unit": False, "cumulative": False, "kind": None}]}]}
        for d in ("a", "b") for v in ("a", "b")
    ]
    path = tmp_path / "pm.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(primary_missions, "OUTPUT_PATH", path)
    battle = client.post("/battles", json={"your_disposition": "a", "opponent_disposition": "a"}).json()
    out = client.patch(
        f"/battles/{battle['id']}/players/1/mission-score", json={"section_index": 0, "tier_index": 0}
    ).json()
    assert out["players"][0]["vp"] == 5

    same = client.patch(f"/battles/{battle['id']}/setup", json={"your_disposition": "a"}).json()
    assert same["players"][0]["vp"] == 5 and same["mission_scores"]

    out = client.patch(f"/battles/{battle['id']}/setup", json={"your_disposition": "b"}).json()
    assert out["mission_scores"] == []
    assert all(p["vp"] == 0 for p in out["players"])
    assert client.patch(f"/battles/{battle['id']}/setup", json={"opponent_roster_id": 999}).status_code == 404
    assert client.post("/battles", json={"roster_id": 999}).status_code == 404
    assert client.post("/battles", json={"opponent_roster_id": 999}).status_code == 404


# 6. cascades

def test_delete_unit_removes_synergies_effects_turn_states(client, session):
    _defn(session, "d")
    roster = _roster(client)
    a, b = _unit(client, roster, "d"), _unit(client, roster, "d")
    syn = client.post(
        f"/rosters/{roster['id']}/synergies",
        json={"source_unit_id": a["id"], "target_unit_id": b["id"], "trigger_phase": "command"},
    ).json()
    battle = client.post("/battles", json={"roster_id": roster["id"]}).json()
    client.post(f"/battles/{battle['id']}/synergies/{syn['id']}/acknowledge")
    client.post(
        f"/battles/{battle['id']}/effects",
        json={"label": "e", "owner_player": 1, "duration_type": "end_of_turn", "unit_id": a["id"]},
    )
    client.patch(f"/battles/{battle['id']}/units/{a['id']}/turn-state", json={"has_shot": True})

    assert client.delete(f"/rosters/{roster['id']}/units/{a['id']}").status_code == 204
    for model in (UnitSynergy, SynergyAcknowledgment, ActiveEffect, UnitTurnState):
        assert session.exec(select(model)).all() == []


def test_delete_pool_and_synergy_cascade(client, session):
    _defn(session, "d")
    roster = _roster(client)
    a, b = _unit(client, roster, "d"), _unit(client, roster, "d")
    battle = client.post("/battles", json={"roster_id": roster["id"]}).json()
    p1 = client.post(f"/rosters/{roster['id']}/pools", json={"name": "P", "max_value": 2, "scope": "turn"}).json()
    p2 = client.post(
        f"/rosters/{roster['id']}/pools", json={"name": "S", "max_value": 0, "scope": "turn", "stacking": True}
    ).json()
    client.post(f"/battles/{battle['id']}/pools/{p1['id']}/spend", json={})
    client.post(f"/battles/{battle['id']}/pools/{p2['id']}/add", json={"owner_player": 1, "value": 1})
    syn = client.post(
        f"/rosters/{roster['id']}/synergies",
        json={"source_unit_id": a["id"], "target_unit_id": b["id"], "trigger_phase": "command"},
    ).json()
    client.post(f"/battles/{battle['id']}/synergies/{syn['id']}/acknowledge")

    client.delete(f"/rosters/{roster['id']}/pools/{p1['id']}")
    client.delete(f"/rosters/{roster['id']}/pools/{p2['id']}")
    client.delete(f"/rosters/{roster['id']}/synergies/{syn['id']}")
    for model in (DeclaredStatePoolState, DeclaredStatePoolEntry, SynergyAcknowledgment):
        assert session.exec(select(model)).all() == []


def test_delete_roster_keeps_opponent_battle_and_cleans_its_units(client, session):
    _defn(session, "d")
    mine, theirs = _roster(client), _roster(client)
    their_unit = _unit(client, theirs, "d")
    own_battle = client.post("/battles", json={"roster_id": theirs["id"]}).json()
    battle = client.post("/battles", json={"roster_id": mine["id"], "opponent_roster_id": theirs["id"]}).json()
    client.patch(f"/battles/{battle['id']}/units/{their_unit['id']}/turn-state", json={"has_shot": True})
    client.post(
        f"/battles/{battle['id']}/effects",
        json={"label": "e", "owner_player": 2, "duration_type": "end_of_turn"},
    )
    session.add(MissionScoreEntry(battle_session_id=own_battle["id"], player_number=1, section_index=0, tier_index=0))
    session.commit()

    assert client.delete(f"/rosters/{theirs['id']}").status_code == 204
    kept = client.get(f"/battles/{battle['id']}").json()
    assert kept["opponent_roster_id"] is None and kept["turn_states"] == []
    assert len(kept["effects"]) == 1
    assert client.get(f"/battles/{own_battle['id']}").status_code == 404
    assert session.exec(select(MissionScoreEntry)).all() == []
    assert session.get(Roster, mine["id"]) is not None


def test_delete_battle_removes_everything_it_owns(client, session):
    battle = client.post("/battles", json={}).json()
    client.post(
        f"/battles/{battle['id']}/effects", json={"label": "e", "owner_player": 1, "duration_type": "end_of_turn"}
    )
    session.add(MissionScoreEntry(battle_session_id=battle["id"], player_number=1, section_index=0, tier_index=0))
    session.commit()
    assert client.delete(f"/battles/{battle['id']}").status_code == 204
    assert client.delete(f"/battles/{battle['id']}").status_code == 404
    assert session.exec(select(BattleSession)).all() == []
    assert session.exec(select(ActiveEffect)).all() == []
    assert session.exec(select(MissionScoreEntry)).all() == []


# 7/8. loader

def test_reference_loader_and_find_mission(tmp_path):
    assert reference_data.load_reference_json(tmp_path / "missing.json") == []
    f = tmp_path / "x.json"
    f.write_text('[{"deck": "a", "vs": "b"}]', encoding="utf-8")
    missions = reference_data.load_reference_json(f)
    assert reference_data.find_mission(missions, "a", "b") == missions[0]
    assert reference_data.find_mission(missions, "b", "a") is None
    assert (reference_data.REPO_ROOT / "backend").is_dir()


# 9. CORS

def test_cors_allows_private_lan_and_docker_origins(client):
    def allowed(origin):
        r = client.get("/health", headers={"Origin": origin})
        return r.headers.get("access-control-allow-origin") == origin

    for ok in (
        "http://192.168.1.5:5173", "http://10.0.0.7:5174", "http://172.16.3.4:5173", "http://172.31.255.1:5173",
        "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost", "http://10.1.2.3",
    ):
        assert allowed(ok), ok
    for bad in ("http://172.32.0.1:5173", "http://8.8.8.8:5173", "http://localhost:9999", "https://localhost"):
        assert not allowed(bad), bad


# 10. UnitUpdate validation

def test_unit_update_validation(client, session):
    _defn(session, "d")
    roster = _roster(client)
    unit = _unit(client, roster, "d")
    url = f"/rosters/{roster['id']}/units/{unit['id']}"
    assert client.patch(url, json={"quantity": 0}).status_code == 422
    assert client.patch(url, json={"quantity": None}).status_code == 422
    assert client.patch(url, json={"model_groups": [{"name": " ", "count": 1}]}).status_code == 422
    assert client.patch(url, json={"model_groups": [{"name": "A", "count": -1}]}).status_code == 422
    assert client.patch(url, json={"model_groups": [{"name": "A"}]}).status_code == 422
    assert client.patch(url, json={"quantity": 2, "model_groups": [{"name": "A", "count": 0}]}).status_code == 200
