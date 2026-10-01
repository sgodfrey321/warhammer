from __future__ import annotations

from app import phases
from app.models import UnitDefinition


def test_transition_type_classifies_every_boundary():
    # steps 0-3: command/movement/shooting/charge of player 1's turn -> phase_end
    for step in range(4):
        assert phases.transition_type(step) == "phase_end"
    # step 4: player 1's fight phase ending -> hands to player 2, same round
    assert phases.transition_type(4) == "turn_end"
    for step in range(5, 9):
        assert phases.transition_type(step) == "phase_end"
    # step 9: player 2's fight phase ending -> battle round rolls over
    assert phases.transition_type(9) == "battle_round_end"


def test_scopes_ending():
    assert phases.scopes_ending("phase_end") == {"phase"}
    assert phases.scopes_ending("turn_end") == {"phase", "turn"}
    assert phases.scopes_ending("battle_round_end") == {"phase", "turn", "battle_round"}


def test_end_of_turn_is_owner_relative():
    # Effect owned by player 1, created during player 1's own turn (step 0):
    # must expire once player 1's turn ends (step 5, into player 2's turn).
    assert not phases.is_expired(duration_type="end_of_turn", owner_player=1, created_at_step=0, current_step=4)
    assert phases.is_expired(duration_type="end_of_turn", owner_player=1, created_at_step=0, current_step=5)

    # Effect owned by player 1 but somehow created during player 2's turn (step 5) --
    # must NOT flag when player 2's turn ends (step 10); only when player 1's own
    # next turn ends (step 15).
    assert not phases.is_expired(duration_type="end_of_turn", owner_player=1, created_at_step=5, current_step=10)
    assert not phases.is_expired(duration_type="end_of_turn", owner_player=1, created_at_step=5, current_step=14)


def test_eligibility_warning():
    assert phases.eligibility_warning(move_type=None, has_shot=True, has_charged=False) is None
    assert phases.eligibility_warning(move_type="normal", has_shot=True, has_charged=False) is None
    assert phases.eligibility_warning(move_type="advance", has_shot=False, has_charged=False) is None

    w = phases.eligibility_warning(move_type="advance", has_shot=True, has_charged=False)
    assert w is not None and "Advanced" in w and "shoot" in w

    w = phases.eligibility_warning(move_type="fall_back", has_shot=True, has_charged=True)
    assert w is not None and "Fell Back" in w and "shoot" in w and "charge" in w


def _seed_unit(session, uid="u1", name="Test Unit"):
    session.add(
        UnitDefinition(
            id=uid, faction="Aeldari - Craftworlds", name=name, points_cost=10,
            keywords=[], source_catalogue_id="cat", source_entry_id=uid,
        )
    )
    session.commit()


def _create_roster_and_battle(client):
    roster = client.post("/rosters", json={"name": "Test", "faction": "Aeldari - Craftworlds"}).json()
    battle = client.post("/battles", json={"roster_id": roster["id"]}).json()
    return roster, battle


def test_cp_granted_on_every_command_phase_not_once_per_round(client):
    _, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]

    def cp(b):
        return {p["player_number"]: p["cp_gained"] for p in b["players"]}

    assert cp(battle) == {1: 0, 2: 0}  # starting Command phase doesn't itself grant

    for _ in range(5):  # advance to step 5: player 2's command phase
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert battle["current_phase"] == "command"
    assert cp(battle) == {1: 1, 2: 1}  # both players gain, not just the active one

    for _ in range(5):  # advance to step 10: player 1's command phase, round 2
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert cp(battle) == {1: 2, 2: 2}


def test_non_stacking_pool_refills_at_battle_round_boundary(client, session):
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    pool = client.post(
        f"/rosters/{roster['id']}/pools",
        json={"name": "Battle Focus", "max_value": 4, "scope": "battle_round", "stacking": False},
    ).json()

    # A pool starts full (available from turn 1). Spend it down as player 1.
    battle = client.post(f"/battles/{battle_id}/pools/{pool['id']}/spend", json={"amount": 3}).json()
    state = next(s for s in battle["pool_states"] if s["owner_player"] == 1)
    assert state["current_value"] == 1  # 4 - 3

    # Advancing within the round / to the opponent's turn must NOT refill it.
    for _ in range(5):
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    state = next(s for s in battle["pool_states"] if s["owner_player"] == 1)
    assert state["current_value"] == 1

    # Crossing the battle-round boundary (step 9 -> 10) refills to max.
    for _ in range(5):
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert battle["battle_round"] == 2
    state = next(s for s in battle["pool_states"] if s["owner_player"] == 1)
    assert state["current_value"] == 4


def test_stacking_pool_clears_at_every_phase_boundary(client, session):
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    pool = client.post(
        f"/rosters/{roster['id']}/pools",
        json={"name": "Blessings of Khorne", "max_value": 0, "scope": "phase", "stacking": True},
    ).json()

    battle = client.post(f"/battles/{battle_id}/pools/{pool['id']}/add", json={"owner_player": 1, "value": 3}).json()
    battle = client.post(f"/battles/{battle_id}/pools/{pool['id']}/add", json={"owner_player": 1, "value": 5}).json()
    assert len(battle["pool_entries"]) == 2

    battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert battle["pool_entries"] == []


def test_spend_rejected_for_stacking_pool_and_add_rejected_for_non_stacking(client):
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    stacking_pool = client.post(
        f"/rosters/{roster['id']}/pools",
        json={"name": "Stacking", "max_value": 0, "scope": "phase", "stacking": True},
    ).json()
    plain_pool = client.post(
        f"/rosters/{roster['id']}/pools",
        json={"name": "Plain", "max_value": 4, "scope": "turn", "stacking": False},
    ).json()

    resp = client.post(f"/battles/{battle_id}/pools/{stacking_pool['id']}/spend", json={"amount": 1})
    assert resp.status_code == 422
    resp = client.post(f"/battles/{battle_id}/pools/{plain_pool['id']}/add", json={"owner_player": 1, "value": 1})
    assert resp.status_code == 422


def test_synergy_acknowledgment_reappears_next_phase_instance(client, session):
    _seed_unit(session, "u1", "Farseer")
    _seed_unit(session, "u2", "Dire Avengers")
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    source = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "u1"}).json()
    target = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "u2"}).json()
    synergy = client.post(
        f"/rosters/{roster['id']}/synergies",
        json={"source_unit_id": source["id"], "target_unit_id": target["id"], "trigger_phase": "shooting"},
    ).json()

    for _ in range(2):  # step 2: shooting phase
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert len(battle["active_synergies"]) == 1

    battle = client.post(f"/battles/{battle_id}/synergies/{synergy['id']}/acknowledge").json()
    assert battle["active_synergies"] == []

    # Leave and come back to a shooting phase (next turn's shooting phase, step 7) --
    # the acknowledgment was for a specific step, so it must reappear.
    for _ in range(5):
        battle = client.patch(f"/battles/{battle_id}/advance-phase").json()
    assert battle["current_phase"] == "shooting"
    assert len(battle["active_synergies"]) == 1


def test_turn_state_includes_eligibility_warning(client, session):
    _seed_unit(session, "u1", "Windriders")
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    unit = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "u1"}).json()

    state = client.patch(
        f"/battles/{battle_id}/units/{unit['id']}/turn-state", json={"move_type": "advance"}
    ).json()
    assert state["eligibility_warning"] is None

    state = client.patch(
        f"/battles/{battle_id}/units/{unit['id']}/turn-state", json={"has_shot": True}
    ).json()
    assert state["eligibility_warning"] is not None
    assert "shoot" in state["eligibility_warning"]

    battle = client.get(f"/battles/{battle_id}").json()
    assert battle["turn_states"][0]["eligibility_warning"] is not None


def test_is_fights_first_is_informational_only(client, session):
    _seed_unit(session, "u1", "Khorne Berzerkers")
    roster, battle = _create_roster_and_battle(client)
    battle_id = battle["id"]
    unit = client.post(f"/rosters/{roster['id']}/units", json={"unit_definition_id": "u1"}).json()

    state = client.patch(
        f"/battles/{battle_id}/units/{unit['id']}/turn-state", json={"is_fights_first": True, "has_fought": True}
    ).json()
    assert state["is_fights_first"] is True
    assert state["has_fought"] is True
