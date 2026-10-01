from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import tier1, tier2
from .models import SynergyCandidate, hash_text
from ..util import slugify


def _flatten_abilities(units) -> list[tier2.PendingAbility]:
    items = []
    for unit in units:
        for ability in unit.abilities:
            if not ability.text or not ability.text.strip():
                continue
            items.append(
                tier2.PendingAbility(
                    source_entry_id=unit.source_entry_id or unit.id,
                    unit_name=unit.name,
                    ability_name=ability.name,
                    text=ability.text,
                )
            )
    return items


def _previous_index(previous_candidates: list[SynergyCandidate]) -> dict[tuple[str, str], SynergyCandidate]:
    return {(c.source_entry_id, c.ability_name): c for c in previous_candidates}


def enrich_faction(
    units,
    previous_candidates: list[SynergyCandidate] | None,
    *,
    client=None,
    model: str = tier2.DEFAULT_MODEL,
    poll_interval_seconds: float = 10.0,
) -> list[SynergyCandidate]:
    """Extract a SynergyCandidate for every non-empty ability across `units`.

    Reuses a previous run's record when the ability's current text hash matches SPEC.md's
    caching requirement -- the previous output file *is* the memo table (no separate cache
    store to keep in sync). Anything Tier 1 can't confidently resolve is batched through
    Tier 2 in one call. Pass `client=None` to skip Tier 2 entirely (a Tier-1-only run needs
    no API key, no cost, no network).
    """
    previous_by_key = _previous_index(previous_candidates or [])
    resolved: list[SynergyCandidate] = []
    needs_tier2: list[tier2.PendingAbility] = []

    for item in _flatten_abilities(units):
        key = (item.source_entry_id, item.ability_name)
        current_hash = hash_text(item.text)
        previous = previous_by_key.get(key)
        if previous is not None and previous.text_hash == current_hash:
            resolved.append(previous)
            continue

        tier1_result = tier1.extract(item.source_entry_id, item.unit_name, item.ability_name, item.text)
        if tier1_result is not None:
            resolved.append(tier1_result)
        else:
            needs_tier2.append(item)

    if needs_tier2 and client is not None:
        resolved.extend(
            tier2.run_batch(client, needs_tier2, model=model, poll_interval_seconds=poll_interval_seconds)
        )

    return resolved


def load_previous(path: Path) -> list[SynergyCandidate]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [SynergyCandidate(**c) for c in data.get("candidates", [])]


def emit(faction: str, candidates: list[SynergyCandidate], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{slugify(faction)}-synergies.json"
    payload = {
        "faction": faction,
        "candidates": [
            asdict(c) for c in sorted(candidates, key=lambda c: (c.source_entry_id, c.ability_name))
        ],
    }
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out_path
