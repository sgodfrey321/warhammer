from __future__ import annotations

import json

from app.routers import army_rules


def test_list_army_rules_reads_the_indexer_output(client, monkeypatch, tmp_path):
    payload = [{"faction": "Aeldari - Aeldari Library", "rules": [{"name": "Battle Focus", "text": "Spend tokens."}]}]
    out_path = tmp_path / "army-rules.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(army_rules, "OUTPUT_PATH", out_path)

    resp = client.get("/army-rules")
    assert resp.status_code == 200
    assert resp.json() == payload


def test_list_army_rules_returns_empty_when_output_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(army_rules, "OUTPUT_PATH", tmp_path / "does-not-exist.json")

    resp = client.get("/army-rules")
    assert resp.status_code == 200
    assert resp.json() == []
