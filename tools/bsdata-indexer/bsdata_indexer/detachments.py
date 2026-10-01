"""Extracts each faction's detachment options and their own Detachment Rule -- e.g. Aeldari's
Aspect Host -> "Path of the Warrior", World Eaters' Khorne Daemonkin -> "Blood Tithe".

Distinct from army_rules.py: an army-wide rule (Battle Focus) is gated per-unit via a
structured infoLinks[type=="rule"] link, so eligible units can be found by data alone. A
Detachment Rule is embedded directly on the detachment's own selectionEntry as a `rules`
array, and states its own eligibility in the rule text itself (e.g. "Aspect Warriors or
Avatar of Khaine unit") rather than via a link -- there's no structured per-unit signal to
auto-filter from here; the app just surfaces the text (matchable by hand against a unit's
already-indexed `keywords` -- "Aspect Warrior" is a real category on Dire Avengers).

Confirmed two different real shapes for where a faction's detachment choices actually live,
both handled here so this isn't faction-specific:
- Aeldari: the faction's own "Detachment" entry links out (via its own entryLinks, type
  selectionEntryGroup) to a *shared* group ("Detachments") in the Aeldari Library, whose
  selectionEntries are the real choices.
- World Eaters: the faction's own "Detachment" entry embeds its options directly in its own
  selectionEntryGroups -- no redirect needed.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .catalogue import LIBRARY_FILENAMES, build_global_library_index, load_json
from .fetch import RepoCache
from .models import Ability


def _shared_groups(doc: dict) -> dict[str, dict]:
    groups = doc["catalogue"].get("sharedSelectionEntryGroups") or []
    return {g["id"]: g for g in groups}


def build_global_group_index(fetch_json) -> dict[str, dict]:
    """Merge every known library's sharedSelectionEntryGroups into one id -> group index,
    the same way catalogue.build_global_library_index does for entries."""
    merged: dict[str, dict] = {}
    for stem in LIBRARY_FILENAMES:
        merged.update(_shared_groups(fetch_json(stem)))
    return merged


def _rule_texts(entry: dict) -> list[Ability]:
    return [
        Ability(name=r.get("name", ""), text=(r.get("description") or "").strip())
        for r in entry.get("rules") or []
        if r.get("name")
    ]


def extract_detachments(faction_doc: dict, entry_index: dict[str, dict], group_index: dict[str, dict]) -> list[dict]:
    """`entry_index`/`group_index` should be global id -> sharedSelectionEntry/
    sharedSelectionEntryGroup indexes merged across every library file (see
    catalogue.build_global_library_index and build_global_group_index above), reused across
    every faction the same way catalogue.py's library_index/profile_index already are. Needed
    because the "Detachment" wrapper entry itself is sometimes external too -- Aeldari -
    Craftworlds resolves it into the Aeldari Library, same as it does for units."""
    cat = faction_doc.get("catalogue")
    if cat is None:
        return []

    detachment_link = next((l for l in cat.get("entryLinks") or [] if l.get("name") == "Detachment"), None)
    if detachment_link is None:
        return []

    combined_entries = {**entry_index, **{e["id"]: e for e in cat.get("sharedSelectionEntries") or []}}
    detachment_entry = combined_entries.get(detachment_link.get("targetId"))
    if detachment_entry is None:
        return []

    combined_groups = {**group_index, **_shared_groups(faction_doc)}

    option_groups = list(detachment_entry.get("selectionEntryGroups") or [])
    for link in detachment_entry.get("entryLinks") or []:
        if link.get("type") != "selectionEntryGroup":
            continue
        target_group = combined_groups.get(link.get("targetId"))
        if target_group is not None:
            option_groups.append(target_group)

    detachments: list[dict] = []
    for group in option_groups:
        for entry in group.get("selectionEntries") or []:
            rules = _rule_texts(entry)
            if not rules:
                continue
            detachments.append(
                {"name": entry.get("name", ""), "rules": [asdict(r) for r in rules]}
            )
    return detachments


def build_all(catalogue_cache: RepoCache) -> list[dict]:
    """One entry per cached catalogue file that has its own detachment options with rules."""
    fetch = lambda stem: load_json(catalogue_cache.get(f"{stem}.json"))  # noqa: E731
    entry_index = build_global_library_index(fetch)
    group_index = build_global_group_index(fetch)
    stems = sorted(n[:-5] for n in catalogue_cache.list_files() if n.endswith(".json"))
    factions = []
    for stem in stems:
        doc = load_json(catalogue_cache.get(f"{stem}.json"))
        detachments = extract_detachments(doc, entry_index, group_index)
        if not detachments:
            continue
        factions.append({"faction": doc["catalogue"].get("name", stem), "detachments": detachments})
    return factions


def emit(factions: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "detachments.json"
    out_path.write_text(json.dumps(factions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
