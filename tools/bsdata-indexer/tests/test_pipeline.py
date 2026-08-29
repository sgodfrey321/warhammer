import json

from bsdata_indexer.enrichment import pipeline
from bsdata_indexer.enrichment.models import SynergyCandidate
from bsdata_indexer.models import Ability, UnitDefinition


def make_unit(source_entry_id, name, abilities):
    return UnitDefinition(
        id=f"faction/{name.lower()}",
        faction="Test Faction",
        name=name,
        abilities=abilities,
        source_entry_id=source_entry_id,
    )


# --- fakes standing in for the `anthropic` client -- no network, no package required ---


class _FakeBlock:
    def __init__(self, type_, text=None):
        self.type = type_
        self.text = text


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeResult:
    def __init__(self, type_, message=None):
        self.type = type_
        self.message = message


class _FakeResultItem:
    def __init__(self, custom_id, result):
        self.custom_id = custom_id
        self.result = result


class _FakeBatch:
    def __init__(self, id_, status):
        self.id = id_
        self.processing_status = status


class _FakeBatchesEndpoint:
    def __init__(self, responses_by_ability_name: dict[str, dict]):
        self._responses = responses_by_ability_name
        self.created_requests = None

    def create(self, requests):
        self.created_requests = requests
        return _FakeBatch("batch_1", "ended")

    def retrieve(self, batch_id):
        return _FakeBatch(batch_id, "ended")

    def results(self, batch_id):
        items = []
        for req in self.created_requests:
            content = req["params"]["messages"][0]["content"]
            ability_name = content.split("Ability: ", 1)[1].split("\n", 1)[0]
            payload = self._responses.get(ability_name)
            if payload is None:
                items.append(_FakeResultItem(req["custom_id"], _FakeResult("errored")))
                continue
            block = _FakeBlock("text", text=json.dumps(payload))
            items.append(_FakeResultItem(req["custom_id"], _FakeResult("succeeded", _FakeMessage([block]))))
        return items


class _FakeMessagesNamespace:
    def __init__(self, responses_by_ability_name):
        self.batches = _FakeBatchesEndpoint(responses_by_ability_name)


class FakeClient:
    def __init__(self, responses_by_ability_name):
        self.messages = _FakeMessagesNamespace(responses_by_ability_name)


class ExplodingClient:
    """Fails the test loudly if Tier 2 is ever invoked when it shouldn't be."""

    @property
    def messages(self):
        raise AssertionError("Tier 2 client was used when everything should have resolved via Tier 1/cache")


# --- tests ---


def test_tier1_resolves_without_needing_a_client():
    unit = make_unit("id-1", "Avatar of Khaine", [Ability("Aura", 'While a friendly ^^Aeldari^^ unit is within 6" of this model, add 1 to Charge rolls.')])
    resolved = pipeline.enrich_faction([unit], previous_candidates=[], client=None)
    assert len(resolved) == 1
    assert resolved[0].tier == "tier1"
    assert resolved[0].affects_keyword == "AELDARI"


def test_falls_back_to_tier2_via_injected_client():
    text = "Some genuinely irregular phrasing that Tier 1's regexes won't match at all."
    unit = make_unit("id-2", "Some Character", [Ability("Weird Rule", text)])
    fake = FakeClient({"Weird Rule": {
        "ability_name": "Weird Rule",
        "affects_keyword": "AELDARI",
        "affects_exclusions": [],
        "trigger_phase": "fight",
        "trigger_detail": "when this model fights",
        "duration_type": "manual",
        "confidence": "low",
    }})
    resolved = pipeline.enrich_faction([unit], previous_candidates=[], client=fake)
    assert len(resolved) == 1
    c = resolved[0]
    assert c.tier == "tier2"
    assert c.confidence == "low"
    assert c.affects_keyword == "AELDARI"
    assert c.trigger_phase == "fight"


def test_reuses_previous_record_when_text_hash_unchanged():
    text = 'While a friendly ^^Aeldari^^ unit is within 6" of this model, add 1 to Charge rolls.'
    unit = make_unit("id-3", "Avatar of Khaine", [Ability("Aura", text)])

    first_pass = pipeline.enrich_faction([unit], previous_candidates=[], client=None)
    assert len(first_pass) == 1

    # Second pass: text unchanged -- should reuse the cached record and never touch tier2,
    # even for a client that would blow up if it were actually called.
    second_pass = pipeline.enrich_faction([unit], previous_candidates=first_pass, client=ExplodingClient())
    assert second_pass == first_pass


def test_changed_ability_text_is_recomputed_not_reused():
    unit_v1 = make_unit("id-4", "Avatar of Khaine", [Ability("Aura", 'friendly ^^Aeldari^^ unit within 6"')])
    v1 = pipeline.enrich_faction([unit_v1], previous_candidates=[], client=None)

    unit_v2 = make_unit("id-4", "Avatar of Khaine", [Ability("Aura", 'friendly ^^Drukhari^^ unit within 6"')])
    v2 = pipeline.enrich_faction([unit_v2], previous_candidates=v1, client=None)

    assert v2[0].affects_keyword == "DRUKHARI"
    assert v2[0].text_hash != v1[0].text_hash


def test_all_tier1_resolved_never_touches_the_client():
    unit = make_unit("id-5", "Avatar of Khaine", [Ability("Aura", 'friendly ^^Aeldari^^ unit within 6"')])
    resolved = pipeline.enrich_faction([unit], previous_candidates=[], client=ExplodingClient())
    assert len(resolved) == 1
    assert resolved[0].tier == "tier1"


def test_emit_and_load_previous_round_trip(tmp_path):
    candidates = [
        SynergyCandidate(
            source_entry_id="id-1",
            unit_name="Avatar of Khaine",
            ability_name="Aura",
            text_hash="sha256:abc",
            tier="tier1",
            confidence="high",
            affects_keyword="AELDARI",
        )
    ]
    out_path = pipeline.emit("Aeldari - Craftworlds", candidates, tmp_path)
    assert out_path.name == "aeldari-craftworlds-synergies.json"

    loaded = pipeline.load_previous(out_path)
    assert loaded == candidates


def test_load_previous_missing_file_returns_empty_list(tmp_path):
    assert pipeline.load_previous(tmp_path / "does-not-exist.json") == []
