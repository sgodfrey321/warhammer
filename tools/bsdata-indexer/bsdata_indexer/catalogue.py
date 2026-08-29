from __future__ import annotations

import json
from dataclasses import dataclass

from .models import Ability


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
    catalogue_points: int | None  # fallback reference only; MFM is authoritative
    resolved: bool  # False if targetId wasn't found in the linked Library catalogue


def load_json(raw: bytes) -> dict:
    return json.loads(raw)


def _shared_entries(doc: dict) -> dict[str, dict]:
    entries = doc["catalogue"].get("sharedSelectionEntries") or []
    return {e["id"]: e for e in entries}


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


def _primary_points(entry: dict) -> int | None:
    for cost in entry.get("costs") or []:
        if cost.get("name") == "pts":
            return cost.get("value")
    return None


def _keywords(entry: dict) -> list[str]:
    return [link["name"] for link in entry.get("categoryLinks") or []]


def _stats(entry: dict) -> dict[str, str]:
    """The entry's own "Unit"-typed profile (M/T/Sv/W/LD/OC), if it has one -- units that are
    themselves wargear/model options attached to a parent (no independent stat line) won't."""
    for profile in entry.get("profiles") or []:
        if profile.get("typeName") == "Unit":
            return {
                c["name"]: c.get("$text", "")
                for c in profile.get("characteristics") or []
                if c.get("$text")
            }
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


def resolve_faction(faction_doc: dict, library_index: dict[str, dict]) -> list[ResolvedEntry]:
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
    """
    own_index = _shared_entries(faction_doc)
    combined_index = {**library_index, **own_index}

    cat = faction_doc["catalogue"]
    resolved: list[ResolvedEntry] = []
    for link in cat.get("entryLinks") or []:
        if link.get("type") != "selectionEntry":
            continue
        target = combined_index.get(link.get("targetId"))
        resolved.append(
            ResolvedEntry(
                entrylink_id=link["id"],
                name=link["name"],
                target_id=link.get("targetId"),
                keywords=_keywords(target) if target else [],
                stats=_stats(target) if target else {},
                abilities=_abilities(target) if target else [],
                catalogue_points=_primary_points(target) if target else None,
                resolved=target is not None,
            )
        )
    return resolved
