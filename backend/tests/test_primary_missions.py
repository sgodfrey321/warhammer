from __future__ import annotations

import json

from app.routers import primary_missions


def _sample_mission() -> dict:
    return {
        "name": "Battlefield Dominance",
        "deck": "take-and-hold",
        "vs": "take-and-hold",
        "sections": [
            {
                "when": "FIRST & SECOND BATTLE ROUND",
                "trigger": "End of your turn",
                "header_kind": None,
                "tiers": [
                    {"text": "You control more objectives.", "vp": 2, "per_unit": False, "cumulative": False, "kind": None}
                ],
            }
        ],
    }


def test_list_primary_missions_reads_the_fetcher_output(client, monkeypatch, tmp_path):
    payload = [_sample_mission()]
    out_path = tmp_path / "primary-missions.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(primary_missions, "OUTPUT_PATH", out_path)

    resp = client.get("/primary-missions")
    assert resp.status_code == 200
    assert resp.json() == payload


def test_list_primary_missions_returns_empty_when_output_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(primary_missions, "OUTPUT_PATH", tmp_path / "does-not-exist.json")

    resp = client.get("/primary-missions")
    assert resp.status_code == 200
    assert resp.json() == []
