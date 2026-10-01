from __future__ import annotations

import json

from app.routers import secondary_missions


def _sample_mission() -> dict:
    return {
        "name": "Beacon",
        "slug": "beacon-defender",
        "when_drawn": "WHEN DRAWN: Select one friendly unit.",
        "action": None,
        "sections": [
            {
                "when": "ANY BATTLE ROUND",
                "trigger": "End of your opponent's turn",
                "rows": [
                    {"text": "Your beacon unit is on the battlefield.", "vp": "3", "or_": False},
                    {"text": "Your beacon unit is not within your territory.", "vp": "5", "or_": True},
                ],
            }
        ],
    }


def test_list_secondary_missions_reads_the_fetcher_output(client, monkeypatch, tmp_path):
    payload = [_sample_mission()]
    out_path = tmp_path / "secondary-missions.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(secondary_missions, "OUTPUT_PATH", out_path)

    resp = client.get("/secondary-missions")
    assert resp.status_code == 200
    assert resp.json() == payload


def test_list_secondary_missions_returns_empty_when_output_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(secondary_missions, "OUTPUT_PATH", tmp_path / "does-not-exist.json")

    resp = client.get("/secondary-missions")
    assert resp.status_code == 200
    assert resp.json() == []
