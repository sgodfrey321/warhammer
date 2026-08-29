from __future__ import annotations

from app.models import UnitDefinition


def _advance(client, battle_id, n=1):
    battle = None
    for _ in range(n):
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    return battle


def test_list_battles_filters_by_roster_and_orders_most_recent_first(client):
    roster_a = client.post("/rosters", json={"name": "A", "faction": "Aeldari - Craftworlds"}).json()
    roster_b = client.post("/rosters", json={"name": "B", "faction": "Aeldari - Craftworlds"}).json()

    battle_a1 = client.post("/battles", json={"roster_id": roster_a["id"]}).json()
    battle_a2 = client.post("/battles", json={"roster_id": roster_a["id"]}).json()
    client.post("/battles", json={"roster_id": roster_b["id"]}).json()

    resp = client.get("/battles", params={"roster_id": roster_a["id"]})
    assert resp.status_code == 200
    ids = [b["id"] for b in resp.json()]
    assert ids == [battle_a2["id"], battle_a1["id"]]  # most recent first

    assert len(client.get("/battles").json()) == 3  # unfiltered lists every battle


def test_phase_round_and_turn_sequence(client):
    battle = client.post("/battles", json={}).json()
    battle_id = battle["id"]

    assert (battle["current_phase"], battle["active_player"], battle["battle_round"]) == (
        "command",
        1,
        1,
    )

    # Advance through player 1's full turn (command -> ... -> fight = 4 steps from command).
    b = _advance(client, battle_id, 4)
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("fight", 1, 1)

    # One more step hands the turn to player 2, back at command, same battle round.
    b = _advance(client, battle_id, 1)
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("command", 2, 1)

    # Advance through player 2's full turn.
    b = _advance(client, battle_id, 4)
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("fight", 2, 1)

    # One more step: battle round increments, back to player 1's command phase.
    b = _advance(client, battle_id, 1)
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("command", 1, 2)


def test_retreat_phase_mirrors_advance_and_stops_at_the_start(client):
    battle = client.post("/battles", json={}).json()
    battle_id = battle["id"]

    b = _advance(client, battle_id, 3)
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("charge", 1, 1)

    b = client.patch(f"/battles/{battle_id}/retreat-phase").json()
    assert (b["current_phase"], b["active_player"], b["battle_round"]) == ("shooting", 1, 1)

    b = client.patch(f"/battles/{battle_id}/retreat-phase").json()
    b = client.patch(f"/battles/{battle_id}/retreat-phase").json()
    assert (b["current_phase"], b["active_player"], b["battle_round"], b["global_step"]) == (
        "command",
        1,
        1,
        0,
    )

    resp = client.patch(f"/battles/{battle_id}/retreat-phase")
    assert resp.status_code == 422


def test_until_next_command_phase_effect_survives_opponents_turn(client):
    """The Farseer 'Doom' case: an effect logged in your Movement phase lasts until
    *your* next Command phase, surviving the opponent's entire intervening turn."""
    battle = client.post("/battles", json={}).json()
    battle_id = battle["id"]

    _advance(client, battle_id, 1)  # step 1: player 1's movement phase

    effect_resp = client.post(
        f"/battles/{battle_id}/effects",
        json={"label": "Doom", "owner_player": 1, "duration_type": "until_next_command_phase"},
    )
    assert effect_resp.status_code == 200
    battle = effect_resp.json()
    effect = battle["effects"][0]
    assert effect["expired"] is False

    # Advance through the rest of player 1's turn and all of player 2's turn.
    b = _advance(client, battle_id, 8)  # step 9: player 2's fight phase
    assert (b["current_phase"], b["active_player"]) == ("fight", 2)
    assert b["effects"][0]["expired"] is False, "must survive the opponent's whole turn"

    # Player 1's next command phase: now it expires.
    b = _advance(client, battle_id, 1)  # step 10: player 1's command phase
    assert (b["current_phase"], b["active_player"]) == ("command", 1)
    assert b["effects"][0]["expired"] is True


def test_end_of_phase_and_end_of_turn_and_end_of_battle_round_expiry(client):
    battle = client.post("/battles", json={}).json()
    battle_id = battle["id"]

    r1 = client.post(
        f"/battles/{battle_id}/effects",
        json={"label": "phase-scoped", "owner_player": 1, "duration_type": "end_of_phase"},
    ).json()
    r2 = client.post(
        f"/battles/{battle_id}/effects",
        json={"label": "turn-scoped", "owner_player": 1, "duration_type": "end_of_turn"},
    ).json()
    r3 = client.post(
        f"/battles/{battle_id}/effects",
        json={"label": "round-scoped", "owner_player": 1, "duration_type": "end_of_battle_round"},
    ).json()

    by_label = {e["label"]: e["expired"] for e in r3["effects"]}
    assert by_label == {"phase-scoped": False, "turn-scoped": False, "round-scoped": False}

    b = _advance(client, battle_id, 1)  # any advance expires the phase-scoped one
    by_label = {e["label"]: e["expired"] for e in b["effects"]}
    assert by_label["phase-scoped"] is True
    assert by_label["turn-scoped"] is False
    assert by_label["round-scoped"] is False

    b = _advance(client, battle_id, 4)  # player 2's turn starts -> player 1's turn has ended
    by_label = {e["label"]: e["expired"] for e in b["effects"]}
    assert by_label["turn-scoped"] is True
    assert by_label["round-scoped"] is False

    b = _advance(client, battle_id, 5)  # battle round 2 begins
    by_label = {e["label"]: e["expired"] for e in b["effects"]}
    assert by_label["round-scoped"] is True


def test_manual_dismiss(client):
    battle = client.post("/battles", json={}).json()
    battle_id = battle["id"]
    r = client.post(
        f"/battles/{battle_id}/effects",
        json={"label": "manual thing", "owner_player": 1, "duration_type": "manual"},
    ).json()
    effect_id = r["effects"][0]["id"]

    b = client.delete(f"/battles/{battle_id}/effects/{effect_id}").json()
    assert b["effects"] == []


def test_synergy_surfaces_only_during_its_trigger_phase(client, session):
    session.add(
        UnitDefinition(
            id="farseer",
            faction="Aeldari - Craftworlds",
            name="Farseer",
            points_cost=80,
            keywords=["Character"],
            source_catalogue_id="cat",
            source_entry_id="farseer",
        )
    )
    session.add(
        UnitDefinition(
            id="dire-avengers",
            faction="Aeldari - Craftworlds",
            name="Dire Avengers",
            points_cost=85,
            keywords=["Aspect Warrior"],
            source_catalogue_id="cat",
            source_entry_id="dire-avengers",
        )
    )
    session.commit()

    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()
    farseer = client.post(
        f"/rosters/{roster['id']}/units", json={"unit_definition_id": "farseer"}
    ).json()
    dire_avengers = client.post(
        f"/rosters/{roster['id']}/units", json={"unit_definition_id": "dire-avengers"}
    ).json()
    client.post(
        f"/rosters/{roster['id']}/synergies",
        json={
            "source_unit_id": farseer["id"],
            "target_unit_id": dire_avengers["id"],
            "trigger_phase": "shooting",
            "note": "Doom before they shoot",
        },
    )

    battle = client.post("/battles", json={"roster_id": roster["id"]}).json()
    battle_id = battle["id"]
    assert battle["active_synergies"] == []

    b = _advance(client, battle_id, 2)  # step 2: shooting phase
    assert b["current_phase"] == "shooting"
    assert len(b["active_synergies"]) == 1
    assert b["active_synergies"][0]["note"] == "Doom before they shoot"

    b = _advance(client, battle_id, 1)  # step 3: charge phase
    assert b["active_synergies"] == []
