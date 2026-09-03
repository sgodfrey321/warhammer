import json
from pathlib import Path

from bsdata_indexer import build

FIXTURES = Path(__file__).parent / "fixtures"


class FakeRepoCache:
    """Stands in for fetch.RepoCache in tests -- serves fixture files by path, no network."""

    def __init__(self, files: dict[str, Path]):
        self._files = files

    def get(self, path: str) -> bytes:
        return self._files[path].read_bytes()


def make_caches():
    catalogue_cache = FakeRepoCache(
        {
            "Aeldari - Craftworlds.json": FIXTURES / "craftworlds.json",
            "Aeldari - Aeldari Library.json": FIXTURES / "aeldari_library.json",
        }
    )
    mfm_cache = FakeRepoCache({"data/aeldari.yaml": FIXTURES / "aeldari_mfm.yaml"})
    return catalogue_cache, mfm_cache


def make_library_index(monkeypatch, catalogue_cache):
    monkeypatch.setattr(build.catalogue, "LIBRARY_FILENAMES", ["Aeldari - Aeldari Library"])
    return build.build_library_index(catalogue_cache)


def make_profile_index(monkeypatch, catalogue_cache):
    monkeypatch.setattr(build.catalogue, "LIBRARY_FILENAMES", ["Aeldari - Aeldari Library"])
    return build.build_profile_index(catalogue_cache)


def make_group_index(monkeypatch, catalogue_cache):
    monkeypatch.setattr(build.catalogue, "LIBRARY_FILENAMES", ["Aeldari - Aeldari Library"])
    return build.build_group_index(catalogue_cache)


def test_build_faction_joins_catalogue_and_mfm(monkeypatch):
    catalogue_cache, mfm_cache = make_caches()
    library_index = make_library_index(monkeypatch, catalogue_cache)
    profile_index = make_profile_index(monkeypatch, catalogue_cache)
    group_index = make_group_index(monkeypatch, catalogue_cache)
    report = build.build_faction(
        "Aeldari - Craftworlds",
        catalogue_cache,
        library_index,
        profile_index,
        group_index,
        mfm_cache,
        available_mfm_slugs={"aeldari"},
    )

    assert report.mfm_slug == "aeldari"
    assert report.mfm_slug_guessed is False
    assert report.unresolved_entrylinks == ["Totally New Unit"]

    units = {u.name: u for u in report.units}
    assert set(units) == {
        "Wraithlord",
        "Wave Serpent",
        "Autarch Skyrunner [Legends]",
        "Dire Avengers",
        "Guardian Defenders",
        "Windriders",
        "Warlock",
        "Avatar of Khaine",
    }
    # "Detachment" (type: "upgrade", a config picker with no stat line) must not appear
    # as if it were a real, empty-stats unit.
    assert "Detachment" not in units

    # Windriders/Warlock resolve their stats via a shared-profile infoLink, not an
    # embedded "Unit" profile -- confirms build_faction actually wires profile_index through.
    assert units["Windriders"].stats["M"] == '14"'
    assert units["Warlock"].stats["M"] == '6"'

    dire_avenger_weapons = {w.name for w in units["Dire Avengers"].weapons}
    assert dire_avenger_weapons == {"Close Combat Weapon", "Avenger shuriken catapult"}

    # Group-inside-a-group weapon (see catalogue.py's Bloodthirster note) flows through the
    # full build pipeline, not just resolve_faction in isolation.
    avatar_weapons = {w.name for w in units["Avatar of Khaine"].weapons}
    assert "➤ The Wailing Doom - Strike" in avatar_weapons

    # Guardian Defenders has two model types (Guardian Defender, Heavy Weapon Platform) --
    # model_profiles keeps both, each scoped to its own weapons, instead of the flat `stats`/
    # `weapons` fields' single-baseline-model heuristic. The Shuriken Cannon is only reachable
    # via a selectionEntryGroup-type entryLink (the "Heavy Weapons" option group) -- confirms
    # that gap is actually fixed through the full build pipeline, not just in isolation.
    guardian_defenders = units["Guardian Defenders"]
    profiles_by_name = {p.name: p for p in guardian_defenders.model_profiles}
    assert set(profiles_by_name) == {"Guardian Defender", "Heavy Weapon Platform"}
    assert profiles_by_name["Guardian Defender"].stats["W"] == "1"
    assert profiles_by_name["Heavy Weapon Platform"].stats["W"] == "2"
    assert {w.name for w in profiles_by_name["Guardian Defender"].ranged_weapons} == {"Shuriken Catapult"}
    assert {w.name for w in profiles_by_name["Heavy Weapon Platform"].ranged_weapons} == {"Shuriken Cannon"}

    wraithlord = units["Wraithlord"]
    assert wraithlord.mfm_matched is True
    assert wraithlord.points[0].points == 125  # MFM value wins over the catalogue's 130
    assert wraithlord.is_legends is False
    assert wraithlord.role == "Monster"
    assert wraithlord.id == "aeldari-craftworlds/wraithlord"
    assert wraithlord.stats["T"] == "10"
    assert wraithlord.abilities[0].name == "Fated Hero"
    assert wraithlord.rules == []

    dire_avengers = units["Dire Avengers"]
    assert dire_avengers.rules == ["Battle Focus"]

    skyrunner = units["Autarch Skyrunner [Legends]"]
    assert skyrunner.is_legends is True  # matched via MFM's own name, not the "[Legends]" suffix
    assert skyrunner.mfm_matched is True


def test_build_faction_unmapped_slug_flags_every_unit_unmatched(monkeypatch):
    catalogue_cache, mfm_cache = make_caches()
    library_index = make_library_index(monkeypatch, catalogue_cache)
    profile_index = make_profile_index(monkeypatch, catalogue_cache)
    group_index = make_group_index(monkeypatch, catalogue_cache)
    report = build.build_faction(
        "Aeldari - Craftworlds",
        catalogue_cache,
        library_index,
        profile_index,
        group_index,
        mfm_cache,
        available_mfm_slugs=set(),  # simulate no MFM data available at all
    )
    assert report.mfm_slug is None
    assert all(not u.mfm_matched for u in report.units)
    assert all(u.points == [] for u in report.units)


def test_emit_is_deterministic_and_git_diffable(monkeypatch, tmp_path):
    catalogue_cache, mfm_cache = make_caches()
    library_index = make_library_index(monkeypatch, catalogue_cache)
    profile_index = make_profile_index(monkeypatch, catalogue_cache)
    group_index = make_group_index(monkeypatch, catalogue_cache)
    report = build.build_faction(
        "Aeldari - Craftworlds",
        catalogue_cache,
        library_index,
        profile_index,
        group_index,
        mfm_cache,
        available_mfm_slugs={"aeldari"},
    )

    path_a = build.emit(report, tmp_path / "run1")
    path_b = build.emit(report, tmp_path / "run2")
    assert path_a.read_text() == path_b.read_text()

    payload = json.loads(path_a.read_text())
    names = [u["name"] for u in payload["units"]]
    assert names == sorted(names)
