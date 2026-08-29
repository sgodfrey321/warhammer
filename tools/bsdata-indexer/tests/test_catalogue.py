import json
from pathlib import Path

from bsdata_indexer import catalogue

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_bytes())


def library_index() -> dict[str, dict]:
    return catalogue.index_library_entries(load("aeldari_library.json"))


def test_resolve_faction_matches_known_points_and_keywords():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index())
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

    wave_serpent = by_name["Wave Serpent"]
    assert wave_serpent.catalogue_points == 115


def test_resolve_faction_flags_unresolvable_target():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index())
    by_name = {e.name: e for e in resolved}

    missing = by_name["Totally New Unit"]
    assert missing.resolved is False
    assert missing.keywords == []
    assert missing.catalogue_points is None


def test_resolve_faction_preserves_legends_suffix_in_name():
    faction_doc = load("craftworlds.json")

    resolved = catalogue.resolve_faction(faction_doc, library_index())
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
