from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from .models import SynergyCandidate, hash_text

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = (
    "You extract structured synergy data from Warhammer 40,000 unit ability text. Ability "
    "conditions are phrased as keywords (e.g. AELDARI, ASPECT WARRIOR), not named units -- "
    "extract the keyword(s) an ability's effect targets, not specific unit names. If a field "
    "genuinely cannot be determined from the text, use null rather than guessing, and set "
    "confidence to \"low\" if any field you did fill in is uncertain."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ability_name": {"type": "string"},
        "affects_keyword": {"type": ["string", "null"]},
        "affects_exclusions": {"type": "array", "items": {"type": "string"}},
        "trigger_phase": {
            "type": ["string", "null"],
            "enum": ["shooting", "movement", "command", "charge", "fight", "any", None],
        },
        "trigger_detail": {"type": ["string", "null"]},
        "duration_type": {
            "type": ["string", "null"],
            "enum": [
                "end_of_phase",
                "end_of_turn",
                "end_of_battle_round",
                "until_next_command_phase",
                "until_condition_clears",
                "manual",
                None,
            ],
        },
        "confidence": {"type": "string", "enum": ["high", "low"]},
    },
    "required": [
        "ability_name",
        "affects_keyword",
        "affects_exclusions",
        "trigger_phase",
        "trigger_detail",
        "duration_type",
        "confidence",
    ],
    "additionalProperties": False,
}


@dataclass
class PendingAbility:
    source_entry_id: str
    unit_name: str
    ability_name: str
    text: str


def _custom_id(pending: PendingAbility) -> str:
    # Batches API requires custom_id to be unique per request and safe as an identifier;
    # source_entry_id alone isn't guaranteed unique across multiple abilities on one unit.
    return f"{pending.source_entry_id}::{hash_text(pending.text)[len('sha256:') :][:16]}"


def build_batch_requests(pending: list[PendingAbility], *, model: str = DEFAULT_MODEL) -> list[dict]:
    """Build the `requests` list for client.messages.batches.create(). Plain dicts, not the
    SDK's `Request`/`MessageCreateParamsNonStreaming` wrappers (TypedDicts -- a plain dict of
    the same shape is accepted at runtime) so this stays testable without the `anthropic`
    package installed; the base indexer must not require it just to import this module."""
    return [
        {
            "custom_id": _custom_id(item),
            "params": {
                "model": model,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"Ability: {item.ability_name}\n\n{item.text}"}],
                "output_config": {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            },
        }
        for item in pending
    ]


def run_batch(
    client,
    pending: list[PendingAbility],
    *,
    model: str = DEFAULT_MODEL,
    poll_interval_seconds: float = 10.0,
) -> list[SynergyCandidate]:
    """Submit one Batches API call for every pending ability, block until it completes, and
    return a SynergyCandidate per successfully-parsed result. A per-item failure (errored/
    canceled/expired/unparseable) is logged and skipped, not raised -- one bad ability
    shouldn't sink the whole batch. Empty `pending` short-circuits without an API call."""
    if not pending:
        return []

    logger.warning(
        "Tier 2: submitting %d abilities to the Batches API (model=%s) -- this spends real money.",
        len(pending),
        model,
    )
    by_custom_id = {_custom_id(item): item for item in pending}
    requests = build_batch_requests(pending, model=model)

    batch = client.messages.batches.create(requests=requests)
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        time.sleep(poll_interval_seconds)

    candidates: list[SynergyCandidate] = []
    for result in client.messages.batches.results(batch.id):
        item = by_custom_id.get(result.custom_id)
        if item is None or result.result.type != "succeeded":
            continue
        text_block = next((b for b in result.result.message.content if b.type == "text"), None)
        if text_block is None:
            continue
        try:
            data = json.loads(text_block.text)
        except (json.JSONDecodeError, AttributeError):
            continue

        candidates.append(
            SynergyCandidate(
                source_entry_id=item.source_entry_id,
                unit_name=item.unit_name,
                ability_name=data.get("ability_name") or item.ability_name,
                text_hash=hash_text(item.text),
                tier="tier2",
                confidence=data.get("confidence", "low"),
                affects_keyword=data.get("affects_keyword"),
                affects_exclusions=data.get("affects_exclusions") or [],
                trigger_phase=data.get("trigger_phase"),
                trigger_detail=data.get("trigger_detail"),
                duration_type=data.get("duration_type"),
            )
        )
    return candidates
