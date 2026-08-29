from __future__ import annotations

import json
from pathlib import Path

from app.battlescribe_import import parse_roster
from app.models import UnitDefinition
from scripts.import_unit_definitions import import_faction_file

HANK_ROSTER = Path(__file__).resolve().parent.parent.parent / "docs" / "Hank 2k.json"
AELDARI_OUTPUT = (
    Path(__file__).resolve().parent.parent.parent / "tools" / "bsdata-indexer" / "output" / "aeldari-craftworlds.json"
)


def _load_hank():
    with HANK_ROSTER.open(encoding="utf-8") as f:
        return json.load(f)


def test_parse_roster_extracts_units_and_config():
    parsed = parse_roster(_load_hank())

    assert parsed.name == "Hank 2k"
    assert parsed.points_total == 1990
    assert parsed.points_limit == 2000
    assert parsed.battle_size == "Strike Force (2000 Point limit)"
    assert parsed.detachments == [{"name": "Aspect Host"}]

    names = [e.name for e in parsed.entries]
    assert len(parsed.entries) == 18
    assert names.count("Striking Scorpions") == 2
    assert "Asurmen" in names  # a single-model "model"-type entry
    assert "Dire Avengers" in names  # a multi-model "unit"-type entry

    # A wargear/model sub-selection nested inside a unit must not leak out as its own entry.
    assert "Dire Avenger Exarch" not in names

    # Every entry carries this export's own (ephemeral) selection id, used to resolve
    # attachments below -- not the stable catalogue id.
    assert all(e.roster_selection_id for e in parsed.entries)


def test_parse_roster_extracts_leader_attachments():
    parsed = parse_roster(_load_hank())
    by_selection_id = {e.roster_selection_id: e.name for e in parsed.entries}

    pairs = {(by_selection_id[leader], by_selection_id[led]) for leader, led in parsed.attachments}
    assert pairs == {
        ("Asurmen", "Dire Avengers"),
        ("Fuegan", "Fire Dragons"),
        ("Jain Zar", "Howling Banshees"),
        ("Lhykhis", "Warp Spiders"),
        ("Farseer Skyrunner", "Windriders"),
    }


def test_parse_roster_extracts_actual_equipped_loadout():
    parsed = parse_roster(_load_hank())
    by_name = {e.name: e for e in parsed.entries}

    windriders = by_name["Windriders"]
    loadout = {item["name"]: item["count"] for item in windriders.loadout}
    # 3 Windriders, each with a Twin shuriken catapult and a close combat weapon --
    # a specific chosen loadout, not just "here's what the unit could carry."
    assert loadout == {"Close combat weapon": 3, "Twin shuriken catapult": 3}

    # Non-uniform squad: the Exarch's items must still be counted (merged into the same
    # unit-level total), not lost just because it's a separate model-group from the rank
    # and file.
    dire_avengers = by_name["Dire Avengers"]
    da_loadout = {item["name"]: item["count"] for item in dire_avengers.loadout}
    assert da_loadout.get("Close Combat Weapon", 0) == 10  # 1 Exarch + 9 rank-and-file
    assert da_loadout.get("Avenger shuriken catapult", 0) == 10  # 1 Exarch + 9 rank-and-file


def test_parse_roster_ids_match_indexer_source_entry_ids():
    parsed = parse_roster(_load_hank())
    with AELDARI_OUTPUT.open(encoding="utf-8") as f:
        indexed_ids = {u["source_entry_id"] for u in json.load(f)["units"]}

    assert all(e.unit_definition_id in indexed_ids for e in parsed.entries)


def test_import_endpoint_creates_roster_and_units(client, session):
    import_faction_file(AELDARI_OUTPUT, session)
    session.commit()

    resp = client.post("/rosters/import", json=_load_hank())
    assert resp.status_code == 200
    result = resp.json()

    assert result["roster"]["name"] == "Hank 2k"
    assert result["roster"]["faction"] == "Aeldari - Craftworlds"
    assert result["roster"]["points_limit"] == 2000
    assert len(result["imported"]) == 18
    assert result["unmatched"] == []

    units = client.get(f"/rosters/{result['roster']['id']}/units").json()
    assert len(units) == 18
    assert any(u["unit_definition"]["name"] == "Asurmen" for u in units)

    assert result["attachments_created"] == 5
    attachments = client.get(f"/rosters/{result['roster']['id']}/attachments").json()
    assert len(attachments) == 5

    unit_name = {u["id"]: u["unit_definition"]["name"] for u in units}
    pairs = {(unit_name[a["leader_unit_id"]], unit_name[a["led_unit_id"]]) for a in attachments}
    assert ("Asurmen", "Dire Avengers") in pairs
    assert ("Jain Zar", "Howling Banshees") in pairs


def test_import_endpoint_reports_unmatched_units(client, session):
    # No UnitDefinitions imported at all -- every unit should come back unmatched,
    # not silently dropped, and the roster should still be created.
    resp = client.post("/rosters/import", json=_load_hank())
    assert resp.status_code == 200
    result = resp.json()

    assert len(result["unmatched"]) == 18
    assert result["imported"] == []
    assert result["roster"]["faction"] == "Xenos - Aeldari"  # falls back to the catalogue name hint
