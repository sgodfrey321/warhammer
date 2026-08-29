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
    roster_selection_id: str  # this export's own ephemeral selection id, e.g. "b8wohrl" --
    # only meaningful within one parse_roster() call, used to resolve `attachments` below.
    loadout: list[dict] = field(default_factory=list)  # [{"name": str, "count": int}]


@dataclass
class ParsedRoster:
    name: str
    faction_hint: str | None
    points_total: int | None
    points_limit: int | None
    battle_size: str | None
    detachments: list[dict] = field(default_factory=list)
    entries: list[ParsedEntry] = field(default_factory=list)
    attachments: list[tuple[str, str]] = field(default_factory=list)  # (leader_selection_id, led_selection_id)


def _loadout(sel: dict) -> list[dict]:
    """Aggregates the unit's actually-equipped wargear by name, summed across every
    model-group. Two different shapes confirmed against a real export, both handled here:

    - A multi-model squad's own `selections` are model-groups (each carrying a `number` of
      models, e.g. "3x Windrider with Twin Shuriken Catapult", `type: "model"`), and each
      model-group's own `selections` are its equipped items (each also carrying a `number`,
      e.g. "3x Twin shuriken catapult") -- two levels deep.
    - A single-model Character/vehicle has no model-group wrapper at all (there's only ever
      one model, so BattleScribe doesn't need one) -- its equipped items sit directly in the
      unit's own `selections`, one level shallower (confirmed on Asurmen: "The Bloody Twins"/
      "The Sword of Asur" are direct children, `type: "upgrade"`, not nested under a
      `type: "model"` wrapper). An earlier version of this function only ever looked two
      levels deep, so every single-model unit's loadout silently came back empty.

    `type == "model"` on a direct child is the signal that it's a model-group wrapper (go one
    level deeper); anything else is treated as an equipped item directly. Aggregated to
    unit-level totals, not kept per-model-group -- matches the app's existing granularity
    (UnitTurnState tracks a whole unit's turn state, not individual models); a non-uniform
    squad (different Exarch weapon) still contributes correctly since each model-group is
    walked separately, just merged into one count per weapon name at the end."""
    counts: dict[str, int] = {}

    def add(name: str | None, count: int) -> None:
        if name:
            counts[name] = counts.get(name, 0) + count

    for child in sel.get("selections") or []:
        if child.get("type") == "model":
            for item in child.get("selections") or []:
                add(item.get("name"), item.get("number") or 0)
        else:
            add(child.get("name"), child.get("number") or 0)

    return [{"name": name, "count": count} for name, count in counts.items()]


def _walk_selections(selections: list[dict], out: list[ParsedEntry], attachments: list[tuple[str, str]]) -> None:
    for sel in selections:
        if sel.get("type") in ("unit", "model"):
            entry_id = sel.get("entryId", "")
            out.append(
                ParsedEntry(
                    unit_definition_id=entry_id.rsplit("::", 1)[-1],
                    name=sel.get("name", ""),
                    roster_selection_id=sel.get("id", ""),
                    loadout=_loadout(sel),
                )
            )
            # A Character attached to this unit shows up as an incoming "group" association
            # (BattleScribe's general leader/bodyguard signal -- checked against the display
            # name too, since "Leading" is what every faction inspected so far uses, but
            # `action` is the more robust field per the schema).
            for assoc in sel.get("incomingAssociations") or []:
                if assoc.get("action") == "group" and assoc.get("from"):
                    attachments.append((assoc["from"], sel["id"]))
            continue  # a unit's own nested model/wargear selections aren't separate units
        if sel.get("selections"):
            _walk_selections(sel["selections"], out, attachments)


def _find_config_choice(selections: list[dict], label: str) -> str | None:
    for sel in selections:
        if sel.get("name") == label and sel.get("selections"):
            return sel["selections"][0].get("name")
    return None


def parse_roster(data: dict) -> ParsedRoster:
    roster = data.get("roster", data)  # tolerate being handed the inner dict directly too
    forces = roster.get("forces", [])

    entries: list[ParsedEntry] = []
    attachments: list[tuple[str, str]] = []
    detachments: list[dict] = []
    battle_size = None
    for force in forces:
        top = force.get("selections", [])
        _walk_selections(top, entries, attachments)
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
        attachments=attachments,
    )
