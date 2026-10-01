import json
from pathlib import Path

from bsdata_indexer import detachments


class FakeRepoCache:
    """Stands in for fetch.RepoCache -- serves in-memory catalogue docs, no network.
    build_all() also fetches every known library file (to build the cross-file group index,
    see build_global_group_index) regardless of what's under test -- unregistered ones fall
    back to an empty catalogue rather than erroring."""

    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    def list_files(self) -> list[str]:
        return list(self._docs.keys())

    def get(self, path: str) -> bytes:
        # library=true satisfies catalogue.index_library_entries' own guard for any of the
        # known library filenames this test doesn't care about.
        return json.dumps(self._docs.get(path, {"catalogue": {"library": True}})).encode("utf-8")


def test_extract_detachments_via_embedded_groups():
    """World Eaters shape: the Detachment entry embeds its options directly."""
    doc = {
        "catalogue": {
            "name": "Chaos - World Eaters",
            "entryLinks": [{"name": "Detachment", "targetId": "det-1", "type": "selectionEntry"}],
            "sharedSelectionEntries": [
                {
                    "id": "det-1",
                    "name": "Detachment",
                    "selectionEntryGroups": [
                        {
                            "selectionEntries": [
                                {
                                    "name": "Khorne Daemonkin",
                                    "rules": [{"name": "Blood Tithe", "description": "Gain tithe points."}],
                                },
                                {"name": "Vessels of Wrath", "rules": []},  # no rule -- must be skipped
                            ]
                        }
                    ],
                }
            ],
        }
    }

    result = detachments.extract_detachments(doc, entry_index={}, group_index={})
    assert result == [
        {"name": "Khorne Daemonkin", "rules": [{"name": "Blood Tithe", "text": "Gain tithe points."}]}
    ]


def test_extract_detachments_via_shared_group_link():
    """Aeldari shape: the Detachment entry links out (via its own entryLinks) to a shared
    group defined in a library file, rather than embedding its options directly."""
    doc = {
        "catalogue": {
            "name": "Aeldari - Craftworlds",
            "entryLinks": [{"name": "Detachment", "targetId": "det-1", "type": "selectionEntry"}],
            "sharedSelectionEntries": [
                {
                    "id": "det-1",
                    "name": "Detachment",
                    "entryLinks": [{"type": "selectionEntryGroup", "targetId": "group-1"}],
                }
            ],
        }
    }
    group_index = {
        "group-1": {
            "selectionEntries": [
                {"name": "Aspect Host", "rules": [{"name": "Path of the Warrior", "description": "Re-roll hits."}]},
            ]
        }
    }

    result = detachments.extract_detachments(doc, entry_index={}, group_index=group_index)
    assert result == [
        {"name": "Aspect Host", "rules": [{"name": "Path of the Warrior", "text": "Re-roll hits."}]}
    ]


def test_extract_detachments_returns_empty_when_no_detachment_link():
    doc = {"catalogue": {"name": "Library - Titans", "entryLinks": []}}
    assert detachments.extract_detachments(doc, entry_index={}, group_index={}) == []


def test_build_all_skips_factions_with_no_detachment_rules():
    cache = FakeRepoCache(
        {
            "Chaos - World Eaters.json": {
                "catalogue": {
                    "name": "Chaos - World Eaters",
                    "entryLinks": [{"name": "Detachment", "targetId": "det-1", "type": "selectionEntry"}],
                    "sharedSelectionEntries": [
                        {
                            "id": "det-1",
                            "name": "Detachment",
                            "selectionEntryGroups": [
                                {
                                    "selectionEntries": [
                                        {
                                            "name": "Khorne Daemonkin",
                                            "rules": [{"name": "Blood Tithe", "description": "x"}],
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            },
            "Library - Titans.json": {
                "catalogue": {"name": "Library - Titans", "library": True, "entryLinks": []}
            },
        }
    )

    factions = detachments.build_all(cache)
    assert factions == [
        {
            "faction": "Chaos - World Eaters",
            "detachments": [{"name": "Khorne Daemonkin", "rules": [{"name": "Blood Tithe", "text": "x"}]}],
        }
    ]


def test_emit_writes_detachments_json(tmp_path: Path):
    factions = [{"faction": "Chaos - World Eaters", "detachments": [{"name": "Khorne Daemonkin", "rules": []}]}]
    out_path = detachments.emit(factions, tmp_path)
    assert out_path == tmp_path / "detachments.json"
    assert json.loads(out_path.read_text(encoding="utf-8")) == factions
