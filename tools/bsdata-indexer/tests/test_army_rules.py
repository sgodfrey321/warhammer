import json
from pathlib import Path

from bsdata_indexer import army_rules


class FakeRepoCache:
    """Stands in for fetch.RepoCache -- serves in-memory catalogue docs, no network."""

    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    def list_files(self) -> list[str]:
        return list(self._docs.keys())

    def get(self, path: str) -> bytes:
        return json.dumps(self._docs[path]).encode("utf-8")


def _doc(name: str, **rules_fields) -> dict:
    return {"catalogue": {"name": name, **rules_fields}}


def test_extract_army_rules_reads_both_rules_and_shared_rules():
    doc = _doc(
        "Aeldari - Aeldari Library",
        rules=[{"name": "Battle Focus", "description": "Spend tokens."}],
    )
    result = army_rules.extract_army_rules(doc)
    assert [(r.name, r.text) for r in result] == [("Battle Focus", "Spend tokens.")]

    doc2 = _doc(
        "Chaos - World Eaters",
        sharedRules=[{"name": "Blessings of Khorne", "description": "Roll dice."}],
    )
    result2 = army_rules.extract_army_rules(doc2)
    assert [(r.name, r.text) for r in result2] == [("Blessings of Khorne", "Roll dice.")]


def test_build_all_skips_files_with_no_rules_and_groups_by_catalogue_name():
    cache = FakeRepoCache(
        {
            "Aeldari - Aeldari Library.json": _doc(
                "Aeldari - Aeldari Library",
                rules=[{"name": "Battle Focus", "description": "Spend tokens."}],
            ),
            "Aeldari - Craftworlds.json": _doc("Aeldari - Craftworlds"),  # no rules of its own
        }
    )
    factions = army_rules.build_all(cache)
    assert factions == [
        {
            "faction": "Aeldari - Aeldari Library",
            "rules": [{"name": "Battle Focus", "text": "Spend tokens."}],
        }
    ]


def test_emit_writes_army_rules_json(tmp_path: Path):
    factions = [{"faction": "Aeldari - Aeldari Library", "rules": [{"name": "Battle Focus", "text": "x"}]}]
    out_path = army_rules.emit(factions, tmp_path)
    assert out_path == tmp_path / "army-rules.json"
    assert json.loads(out_path.read_text(encoding="utf-8")) == factions
