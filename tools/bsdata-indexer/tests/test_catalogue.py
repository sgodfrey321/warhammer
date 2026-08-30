import json
from pathlib import Path

from bsdata_indexer import catalogue

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_bytes())


def library_index() -> dict[str, dict]:
    return catalogue.index_library_entries(load("aeldari_library.json"))


def profile_index() -> dict[str, dict]:
    return catalogue._shared_profiles(load("aeldari_library.json"))


def group_index() -> dict[str, dict]:
    return catalogue._shared_entry_groups(load("aeldari_library.json"))


def test_resolve_faction_matches_known_points_and_keywords():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    wraithlord = by_name["Wraithlord"]
    assert wraithlord.resolved is True
    assert wraithlord.catalogue_points == 130
    assert "Monster" in wraithlord.keywords
    assert "Walker" in wraithlord.keywords
    assert wraithlord.stats == {"M": '8"', "T": "10", "Sv": "2+", "W": "10", "LD": "8+", "OC": "3"}
    assert len(wraithlord.abilities) == 1
    assert wraithlord.abilities[0].name == "Fated Hero"
    assert "re-roll a Hit roll of 1" in wraithlord.abilities[0].text
    assert wraithlord.rules == []  # a Monster -- no Battle Focus link, matches real data

    wave_serpent = by_name["Wave Serpent"]
    assert wave_serpent.catalogue_points == 115


def test_resolve_faction_flags_unresolvable_target():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    missing = by_name["Totally New Unit"]
    assert missing.resolved is False
    assert missing.keywords == []
    assert missing.catalogue_points is None


def test_resolve_faction_resolves_squad_stats_from_nested_selection_entry_groups():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    dire_avengers = by_name["Dire Avengers"]
    # Own entry has no top-level "Unit" profile -- must fall back to the nested
    # rank-and-file model (inside selectionEntryGroups), not the Exarch upgrade option.
    assert dire_avengers.stats == {"M": '7"', "T": "3", "Sv": "4+", "W": "2", "LD": "6+", "OC": "1"}
    assert dire_avengers.abilities[0].name == "Bladestorm"
    assert dire_avengers.rules == ["Battle Focus"]


def test_resolve_faction_resolves_squad_stats_from_nested_selection_entries():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    guardian_defenders = by_name["Guardian Defenders"]
    # Own entry has no top-level "Unit" profile -- must fall back to the nested model
    # under the entry's own `selectionEntries` (the other real shape, no group wrapper).
    assert guardian_defenders.stats == {"M": '6"', "T": "3", "Sv": "4+", "W": "1", "LD": "6+", "OC": "2"}


def test_resolve_faction_keeps_every_nested_model_type_as_its_own_profile():
    # Guardian Defenders has two model types -- "Guardian Defender" (W:1, Shuriken Catapult)
    # and "Heavy Weapon Platform" (W:2, Shuriken Cannon reached via a selectionEntryGroup-type
    # entryLink, not a bare selectionEntry). The flat `stats`/`weapons` fields only ever see
    # the first (see the test above) -- model_profiles must keep both, each scoped to its own
    # weapons only (not the other model's).
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    guardian_defenders = by_name["Guardian Defenders"]
    profiles_by_name = {p.name: p for p in guardian_defenders.model_profiles}
    assert set(profiles_by_name) == {"Guardian Defender", "Heavy Weapon Platform"}

    defender = profiles_by_name["Guardian Defender"]
    assert defender.stats["W"] == "1"
    assert {w.name for w in defender.ranged_weapons} == {"Shuriken Catapult"}

    platform = profiles_by_name["Heavy Weapon Platform"]
    assert platform.stats["W"] == "2"
    assert {w.name for w in platform.ranged_weapons} == {"Shuriken Cannon"}


def test_resolve_faction_resolves_stats_via_shared_profile_info_link():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    # Windriders: nested weapon-loadout entries have no embedded "Unit" profile at all --
    # each links (infoLinks, type "profile") to a shared profile in sharedProfiles instead.
    windriders = by_name["Windriders"]
    assert windriders.stats == {"M": '14"', "T": "4", "Sv": "4+", "W": "2", "LD": "7+", "OC": "2"}

    # Warlock: a single-model entry whose OWN infoLinks (not a nested sub-entry) points at
    # the shared profile -- exercises the top-level (non-nested) info-link resolution path.
    warlock = by_name["Warlock"]
    assert warlock.stats == {"M": '6"', "T": "3", "Sv": "4+", "W": "2", "LD": "6+", "OC": "1"}


def test_resolve_faction_collects_weapons_embedded_and_via_entry_link():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    dire_avengers = by_name["Dire Avengers"]
    weapons_by_name = {w.name: w for w in dire_avengers.weapons}

    # Embedded directly on the (nested) model entry.
    ccw = weapons_by_name["Close Combat Weapon"]
    assert ccw.range_type == "Melee Weapons"
    assert ccw.characteristics == {"Range": "Melee", "A": "2", "WS": "3+", "S": "3", "AP": "0", "D": "1"}

    # Reached via that model entry's own entryLinks, resolved against the shared index.
    catapult = weapons_by_name["Avenger shuriken catapult"]
    assert catapult.range_type == "Ranged Weapons"
    assert catapult.characteristics["BS"] == "3+"

    # The rank-and-file model AND the Exarch both link to the same weapon -- must not
    # appear twice just because it's reachable via two different nested model entries.
    assert len(dire_avengers.weapons) == 2


def test_resolve_faction_collects_weapons_via_shared_profile_info_link():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    windriders = by_name["Windriders"]
    names = {w.name for w in windriders.weapons}
    # Each of the two weapon-loadout variants links to a *different* shared weapon profile --
    # both mutually-exclusive options collected, since this is "what can this unit carry"
    # (catalogue-level reference), not a specific chosen loadout.
    assert names == {"Twin shuriken catapult", "Scatter laser"}


def test_resolve_faction_collects_weapons_nested_inside_a_group_inside_a_group():
    # Real bug, found on the Bloodthirster: a weapon can be nested inside a group that is
    # itself nested inside another group ("Wargear" -> "Replace weapon" -> the actual weapon),
    # not just one level of entry.selectionEntryGroups -> selectionEntries. An earlier version
    # of _weapon_profiles only walked one level and silently dropped weapons at this depth.
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    by_name = {e.name: e for e in resolved}

    avatar = by_name["Avatar of Khaine"]
    names = {w.name for w in avatar.weapons}
    assert names == {"The Wailing Doom", "➤ The Wailing Doom - Strike", "➤ The Wailing Doom - Sweep"}


def test_resolve_faction_excludes_non_unit_config_entries():
    faction_doc = load("craftworlds.json")
    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    names = {e.name for e in resolved}

    # "Detachment" resolves to a real target (type: "upgrade", a config picker, no stat
    # line) -- it must not appear in the output looking like an empty-stats unit.
    assert "Detachment" not in names


def test_resolve_faction_preserves_legends_suffix_in_name():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index(), profile_index(), group_index())
    names = {e.name for e in resolved}
    assert "Autarch Skyrunner [Legends]" in names


def test_index_library_entries_rejects_non_library_catalogue():
    faction_doc = load("craftworlds.json")  # library: false
    try:
        catalogue.index_library_entries(faction_doc)
    except catalogue.CatalogueError:
        pass
    else:
        raise AssertionError("expected CatalogueError for a library=false catalogue")


def test_build_global_library_index_merges_multiple_files(monkeypatch):
    second_library = {
        "catalogue": {
            "id": "second-lib",
            "name": "Second Library",
            "library": True,
            "sharedSelectionEntries": [
                {"id": "target-extra-unit", "name": "Extra Unit", "categoryLinks": [], "costs": []}
            ],
        }
    }
    monkeypatch.setattr(catalogue, "LIBRARY_FILENAMES", ["Aeldari - Aeldari Library", "Second Library"])

    docs = {"Aeldari - Aeldari Library": load("aeldari_library.json"), "Second Library": second_library}
    merged = catalogue.build_global_library_index(lambda stem: docs[stem])

    assert "target-wraithlord" in merged
    assert "target-extra-unit" in merged
