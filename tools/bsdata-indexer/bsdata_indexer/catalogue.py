from __future__ import annotations

import json
from dataclasses import dataclass

from .models import Ability, Weapon

_WEAPON_TYPE_NAMES = ("Ranged Weapons", "Melee Weapons")


class CatalogueError(RuntimeError):
    pass


# Catalogue files with `"library": true` -- shared pools that faction files' entryLinks resolve
# into. Confirmed by fetching each candidate and matching its own `catalogue.id` against the
# targetIds in a real faction file's catalogueLinks (World Eaters links to five of these).
# A faction's catalogueLinks[].name is NOT reliable for finding the right file to fetch --
# World Eaters declares "Chaos - Daemons Library" but the real, current file is named
# "Chaos - Chaos Daemons Library.json"; only the targetId is stable. So instead of resolving
# catalogueLinks by name per faction, every library file is fetched once and merged into one
# global id -> entry index (see build_global_library_index), reused for every faction.
LIBRARY_FILENAMES = [
    "Aeldari - Aeldari Library",
    "Chaos - Chaos Daemons Library",
    "Chaos - Chaos Knights Library",
    "Imperium - Astra Militarum - Library",
    "Imperium - Imperial Knights - Library",
    "Library - Astartes Heresy Legends",
    "Library - Titans",
    "Library - Tyranids",
    "Unaligned Forces",
]


@dataclass
class ResolvedEntry:
    entrylink_id: str
    name: str  # the entryLink's own name -- carries faction-specific overrides / "[Legends]"
    target_id: str | None
    keywords: list[str]
    stats: dict[str, str]  # M/T/Sv/W/LD/OC, from the entry's own "Unit"-typed profile
    abilities: list[Ability]  # from the entry's own "Abilities"-typed profiles
    weapons: list[Weapon]  # every "Ranged/Melee Weapons"-typed profile reachable from the entry
    catalogue_points: int | None  # fallback reference only; MFM is authoritative
    resolved: bool  # False if targetId wasn't found in the linked Library catalogue


def load_json(raw: bytes) -> dict:
    return json.loads(raw)


def _shared_entries(doc: dict) -> dict[str, dict]:
    entries = doc["catalogue"].get("sharedSelectionEntries") or []
    return {e["id"]: e for e in entries}


def _shared_profiles(doc: dict) -> dict[str, dict]:
    """id -> profile, for one catalogue's `sharedProfiles` pool -- a separate top-level array
    from `sharedSelectionEntries`, referenced by `infoLinks[type == "profile"]` (see
    `_info_link_stats`) rather than embedded directly on an entry."""
    profiles = doc["catalogue"].get("sharedProfiles") or []
    return {p["id"]: p for p in profiles}


def index_library_entries(library_doc: dict) -> dict[str, dict]:
    """entry id -> sharedSelectionEntry, for one Library catalogue (library == true)."""
    cat = library_doc["catalogue"]
    if not cat.get("library"):
        raise CatalogueError(f"{cat.get('name')!r}: expected a library=true catalogue")
    return _shared_entries(library_doc)


def build_global_library_index(fetch_json) -> dict[str, dict]:
    """Merge every known library's sharedSelectionEntries into one id -> entry index, shared
    across all factions. `fetch_json(filename_stem) -> dict` loads and parses one file, e.g.
    `lambda stem: catalogue.load_json(catalogue_cache.get(f"{stem}.json"))`."""
    merged: dict[str, dict] = {}
    for stem in LIBRARY_FILENAMES:
        merged.update(index_library_entries(fetch_json(stem)))
    return merged


def build_global_profile_index(fetch_json) -> dict[str, dict]:
    """Merge every known library's sharedProfiles into one id -> profile index, the same way
    build_global_library_index does for entries. `fetch_json` -- see that function."""
    merged: dict[str, dict] = {}
    for stem in LIBRARY_FILENAMES:
        merged.update(_shared_profiles(fetch_json(stem)))
    return merged


def _primary_points(entry: dict) -> int | None:
    for cost in entry.get("costs") or []:
        if cost.get("name") == "pts":
            return cost.get("value")
    return None


def _keywords(entry: dict) -> list[str]:
    return [link["name"] for link in entry.get("categoryLinks") or []]


def _characteristics(profile: dict) -> dict[str, str]:
    return {c["name"]: c.get("$text", "") for c in profile.get("characteristics") or [] if c.get("$text")}


def _stats(entry: dict) -> dict[str, str]:
    """The entry's own "Unit"-typed profile (M/T/Sv/W/LD/OC), if it has one -- units that are
    themselves wargear/model options attached to a parent (no independent stat line) won't."""
    for profile in entry.get("profiles") or []:
        if profile.get("typeName") == "Unit":
            return _characteristics(profile)
    return {}


def _info_link_stats(entry: dict, profile_index: dict[str, dict]) -> dict[str, str]:
    """Some entries don't embed their "Unit" profile at all -- they reference one in the
    catalogue's `sharedProfiles` pool via `infoLinks[type == "profile"]` instead (confirmed
    directly: Warlock, a single-model entry, links to a shared "Warlock" profile this way).
    Same referenced-vs-embedded split as universal rules like Wraithlord's "Feel No Pain" --
    the shared pool just happens to be non-empty for stats in the factions checked so far."""
    for link in entry.get("infoLinks") or []:
        if link.get("type") != "profile":
            continue
        profile = profile_index.get(link.get("targetId"))
        if profile and profile.get("typeName") == "Unit":
            return _characteristics(profile)
    return {}


def _nested_unit_stats(entry: dict, profile_index: dict[str, dict]) -> dict[str, str]:
    """Best-effort fallback for squad units, whose own entry carries no "Unit" profile --
    the base model's stat line lives one level down, in a nested selectionEntry. Real data
    uses two different shapes for this (checked directly): either directly under the entry's
    own `selectionEntries` (e.g. Guardian Defenders -> "Guardian Defender"), or inside a
    `selectionEntryGroups[].selectionEntries` (e.g. Dire Avengers -> group "4-9 Dire
    Avengers" -> "Dire Avenger"). Takes the first nested model found with a "Unit" profile
    (checked either embedded directly, or via `infoLinks` -- e.g. Windriders' weapon-loadout
    variants each link to a shared "Windriders" profile rather than embedding one) as the
    squad's baseline line -- in every shape checked, the rank-and-file model is listed before
    upgrade options (Exarch, heavy weapon), so first-found is normally the unit's actual
    baseline, but this is a heuristic, not a schema guarantee."""
    candidates = list(entry.get("selectionEntries") or [])
    for group in entry.get("selectionEntryGroups") or []:
        candidates.extend(group.get("selectionEntries") or [])
    for sub in candidates:
        stats = _stats(sub) or _info_link_stats(sub, profile_index)
        if stats:
            return stats
    return {}


def _abilities(entry: dict) -> list[Ability]:
    """Every "Abilities"-typed profile embedded directly on the entry (e.g. Wraithlord's
    "Fated Hero"). Doesn't follow `infoLinks` to catalogue- or game-system-level shared rules
    (e.g. universal rules like "Feel No Pain") -- those live outside this Library file, in the
    .gst game system file, not fetched here. Known gap, not silently claimed as complete."""
    abilities: list[Ability] = []
    for profile in entry.get("profiles") or []:
        if profile.get("typeName") != "Abilities":
            continue
        text = "\n".join(
            c["$text"] for c in profile.get("characteristics") or [] if c.get("$text")
        )
        abilities.append(Ability(name=profile.get("name", ""), text=text))
    return abilities


def _weapon_profiles(
    entry: dict, combined_index: dict[str, dict], profile_index: dict[str, dict], *, visited: set[str] | None = None
) -> list[Weapon]:
    """Every weapon profile reachable from this entry's own subtree -- collects the unit's
    full possible loadout (catalogue-level "what can this unit carry"), not a specific chosen
    loadout (that's roster-instance data, see battlescribe_import.py's ParsedEntry.loadout).

    Confirmed against real data: a weapon can be embedded directly on a nested model entry
    (Dire Avenger's "Close Combat Weapon"), reached via that entry's own `entryLinks` (Dire
    Avenger's "Avenger shuriken catapult"), or referenced via `infoLinks[type=="profile"]`
    into `sharedProfiles` (same mechanism as `_info_link_stats`, not yet directly confirmed
    for a weapon specifically but handled the same way for consistency). For a unit with
    mutually-exclusive weapon options (e.g. Windriders' 3 weapon variants), every option is
    collected -- this deliberately doesn't model the option/constraint system, just the set
    of profiles a unit is associated with. `visited` guards against cycles (id-based); none
    seen in real data, but the recursion has no other depth bound.
    """
    if visited is None:
        visited = set()
    entry_id = entry.get("id")
    if entry_id is not None:
        if entry_id in visited:
            return []
        visited.add(entry_id)

    weapons: list[Weapon] = []

    for profile in entry.get("profiles") or []:
        if profile.get("typeName") in _WEAPON_TYPE_NAMES:
            weapons.append(
                Weapon(
                    name=profile.get("name", ""),
                    range_type=profile["typeName"],
                    characteristics=_characteristics(profile),
                )
            )

    for link in entry.get("infoLinks") or []:
        if link.get("type") != "profile":
            continue
        profile = profile_index.get(link.get("targetId"))
        if profile and profile.get("typeName") in _WEAPON_TYPE_NAMES:
            weapons.append(
                Weapon(
                    name=profile.get("name", ""),
                    range_type=profile["typeName"],
                    characteristics=_characteristics(profile),
                )
            )

    nested_groups = [entry] + list(entry.get("selectionEntryGroups") or [])
    for group in nested_groups:
        for sub in group.get("selectionEntries") or []:
            weapons.extend(_weapon_profiles(sub, combined_index, profile_index, visited=visited))
        for link in group.get("entryLinks") or []:
            if link.get("type") != "selectionEntry":
                continue
            target = combined_index.get(link.get("targetId"))
            if target is not None:
                weapons.extend(_weapon_profiles(target, combined_index, profile_index, visited=visited))

    seen_names: set[str] = set()
    deduped: list[Weapon] = []
    for w in weapons:
        if w.name not in seen_names:
            seen_names.add(w.name)
            deduped.append(w)
    return deduped


def resolve_faction(
    faction_doc: dict, library_index: dict[str, dict], profile_index: dict[str, dict]
) -> list[ResolvedEntry]:
    """Resolve every unit entryLink in a faction catalogue.

    Not every faction is a thin index over external libraries the way Aeldari - Craftworlds
    is (it resolves 100% into the external Aeldari Library). World Eaters, checked directly,
    resolves only ~40% of its entryLinks externally (Legends units, Daemon allies via the
    shared libraries) -- the rest, including faction-defining units like Angron, are inline
    in World Eaters' *own* `sharedSelectionEntries`. So every faction's own shared entries are
    merged with the external `library_index` here, own entries taking priority on an id clash.

    Only `type == "selectionEntry"` links are treated as units (matches every real faction
    file inspected so far -- Aeldari - Craftworlds has 106/106 entryLinks of this type, none
    of another type). `sharedSelectionEntryGroups` (option groups, e.g. wargear choices) are
    not resolved into -- SPEC.md flagged this shape as a possible gap; still unhandled here.

    A resolved target's own `type` field is also checked and must be "unit" or "model" --
    without this, catalogue-config entries with no stat line (e.g. "Detachment", a
    battle-size/detachment picker; "Battle Focus - Agile Manoeuvres", a faction rule) come
    back `type: "upgrade"` and were leaking into the output looking like real, empty units.
    Confirmed directly against the real Aeldari data: every genuine unit/model entry
    inspected has `type` set to "unit" or "model", every config/rule wrapper has "upgrade".
    """
    own_index = _shared_entries(faction_doc)
    combined_index = {**library_index, **own_index}
    combined_profiles = {**profile_index, **_shared_profiles(faction_doc)}

    cat = faction_doc["catalogue"]
    resolved: list[ResolvedEntry] = []
    for link in cat.get("entryLinks") or []:
        if link.get("type") != "selectionEntry":
            continue
        target = combined_index.get(link.get("targetId"))
        if target is not None and target.get("type") not in ("unit", "model"):
            continue
        resolved.append(
            ResolvedEntry(
                entrylink_id=link["id"],
                name=link["name"],
                target_id=link.get("targetId"),
                keywords=_keywords(target) if target else [],
                stats=(
                    (
                        _stats(target)
                        or _info_link_stats(target, combined_profiles)
                        or _nested_unit_stats(target, combined_profiles)
                    )
                    if target
                    else {}
                ),
                abilities=_abilities(target) if target else [],
                weapons=_weapon_profiles(target, combined_index, combined_profiles) if target else [],
                catalogue_points=_primary_points(target) if target else None,
                resolved=target is not None,
            )
        )
    return resolved
