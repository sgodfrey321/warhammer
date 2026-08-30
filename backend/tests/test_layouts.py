from __future__ import annotations

import json

from app.routers import layouts


def _sample_matchup() -> dict:
    return {
        "deck": "take-and-hold",
        "vs": "take-and-hold",
        "name": "Take and Hold Mirror",
        "layouts": [
            {
                "number": 1,
                "name": "Layout 1",
                "image": "https://gdmissions.app/assets/11th/layouts/no-measurements/take-and-hold-mirror-1.png",
                "measurements_image": "https://gdmissions.app/assets/11th/layouts/with-measurements/take-and-hold-mirror-1.png",
            }
        ],
    }


def test_list_layouts_reads_the_fetcher_output(client, monkeypatch, tmp_path):
    payload = [_sample_matchup()]
    out_path = tmp_path / "layouts.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(layouts, "OUTPUT_PATH", out_path)

    resp = client.get("/layouts")
    assert resp.status_code == 200
    assert resp.json() == payload


def test_list_layouts_returns_empty_when_output_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(layouts, "OUTPUT_PATH", tmp_path / "does-not-exist.json")

    resp = client.get("/layouts")
    assert resp.status_code == 200
    assert resp.json() == []
