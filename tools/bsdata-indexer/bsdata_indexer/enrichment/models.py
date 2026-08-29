from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# Canonical value sets -- both tiers must emit only these, so downstream consumers never see
# tier-specific vocabulary.
TRIGGER_PHASES = {"command", "movement", "shooting", "charge", "fight", "any"}
DURATION_TYPES = {
    "end_of_phase",
    "end_of_turn",
    "end_of_battle_round",
    "until_next_command_phase",
    "until_condition_clears",
    "manual",
}


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class SynergyCandidate:
    source_entry_id: str  # joins back to UnitDefinition.source_entry_id
    unit_name: str  # denormalized for readability, not for joining
    ability_name: str
    text_hash: str  # hash_text() of the ability text this was extracted from
    tier: str  # "tier1" | "tier2"
    confidence: str  # "high" | "low"
    affects_keyword: str | None = None
    affects_exclusions: list[str] = field(default_factory=list)
    trigger_phase: str | None = None
    trigger_detail: str | None = None
    duration_type: str | None = None
