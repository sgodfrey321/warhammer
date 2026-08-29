"""Parses a BattleScribe/NewRecruit roster export JSON into importable roster entries.

Pure parsing, no DB access -- keeps this testable without a database and reusable
from both the API endpoint and any future standalone script.

Join strategy: each unit/model selection's `entryId` is `<linkId>::<targetId>`, and
`targetId` is exactly the catalogue entry id the bsdata-indexer already uses as
`UnitDefinition.id` (confirmed directly against a real NewRecruit export). So matching
is an exact id lookup, not fuzzy name matching -- `rsplit("::", 1)[-1]` on a bare id
with no separator just returns it unchanged, so this also tolerates exports that don't
use the linkId::targetId form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_POINTS_LIMIT_RE = re.compile(r"\((\d+)\s*Point limit\)", re.IGNORECASE)


@dataclass
class ParsedEntry:
    unit_definition_id: str
    name: str


@dataclass
class ParsedRoster:
    name: str
    faction_hint: str | None
    points_total: int | None
    points_limit: int | None
    battle_size: str | None
    detachments: list[dict] = field(default_factory=list)
    entries: list[ParsedEntry] = field(default_factory=list)


def _walk_selections(selections: list[dict], out: list[ParsedEntry]) -> None:
    for sel in selections:
        if sel.get("type") in ("unit", "model"):
            entry_id = sel.get("entryId", "")
            out.append(ParsedEntry(unit_definition_id=entry_id.rsplit("::", 1)[-1], name=sel.get("name", "")))
            continue  # a unit's own nested model/wargear selections aren't separate units
        if sel.get("selections"):
            _walk_selections(sel["selections"], out)


def _find_config_choice(selections: list[dict], label: str) -> str | None:
    for sel in selections:
        if sel.get("name") == label and sel.get("selections"):
            return sel["selections"][0].get("name")
    return None


def parse_roster(data: dict) -> ParsedRoster:
    roster = data.get("roster", data)  # tolerate being handed the inner dict directly too
    forces = roster.get("forces", [])

    entries: list[ParsedEntry] = []
    detachments: list[dict] = []
    battle_size = None
    for force in forces:
        top = force.get("selections", [])
        _walk_selections(top, entries)
        detachment_name = _find_config_choice(top, "Detachment")
        if detachment_name:
            detachments.append({"name": detachment_name})
        if battle_size is None:
            battle_size = _find_config_choice(top, "Battle Size")

    points_total = None
    for cost in roster.get("costs", []):
        if cost.get("name") == "pts":
            points_total = int(cost["value"])

    points_limit = None
    if battle_size:
        m = _POINTS_LIMIT_RE.search(battle_size)
        if m:
            points_limit = int(m.group(1))

    return ParsedRoster(
        name=roster.get("name") or "Imported Roster",
        faction_hint=forces[0].get("catalogueName") if forces else None,
        points_total=points_total,
        points_limit=points_limit,
        battle_size=battle_size,
        detachments=detachments,
        entries=entries,
    )
