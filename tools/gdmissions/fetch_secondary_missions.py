"""Fetches 11th-edition secondary mission cards from gdmissions.app -- see fetch_missions.py
for the shared fetch/parse approach (same site, same Next.js flight-payload trick).

Secondary missions are NOT deck-organized the way primary missions are -- a single flat list
of 18 cards (confirmed live: "CARD 04/18" on the Beacon card), no attacker/defender split
found for 11th edition despite the site's own homepage copy mentioning one (that may be a
10th-edition-only distinction, or a future addition -- not present in the real 11th data
crawled here).

Their JSON shape also genuinely differs from primary missions, confirmed against two real
cards: Cleanse has a Battlefield Action (`action: {title, rows: [{k, v}]}`, e.g. STARTS/UNITS/
USE LIMIT/COMPLETES/EFFECT) and no `whenDrawn`; Beacon has a `whenDrawn` instruction and no
`action`. Both are optional here, not assumed present. `sections[].rows[]` (not `tiers[]` like
primary missions) carry `vp` as a **string** ("3", not 3) and an `or` flag instead of
`cumulative`/`perUnit` -- kept as-is rather than coerced, matching this project's "surface
what's really there" convention. Text uses HTML tags (`<b>`, `<span class="cB__mark">`) instead
of primary missions' markdown -- left untouched here too; the caller decides how to render it.

Like fetch_missions.py: this is a fan site, not GW/BSData, and the mission text is still GW's
copyrighted rules content -- personal reference only.

Usage: python fetch_secondary_missions.py [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _shared import extract_links, extract_object_with_key, fetch, iter_push_payloads, new_session

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class ActionRow:
    k: str
    v: str


@dataclass(frozen=True)
class Action:
    title: str
    rows: list[ActionRow] = field(default_factory=list)


@dataclass(frozen=True)
class SecondaryRow:
    text: str
    vp: str  # kept as a string -- real data has it as one, not coerced to int
    or_: bool = False


@dataclass(frozen=True)
class SecondarySection:
    when: str
    trigger: str | None = None
    rows: list[SecondaryRow] = field(default_factory=list)


@dataclass(frozen=True)
class SecondaryMission:
    name: str
    slug: str
    when_drawn: str | None = None
    action: Action | None = None
    sections: list[SecondarySection] = field(default_factory=list)


def parse_secondary_mission_page(html: str, slug: str) -> SecondaryMission | None:
    for payload in iter_push_payloads(html):
        obj = extract_object_with_key(payload, "sections")
        if obj is None or "name" not in obj:
            continue

        action = None
        if obj.get("action"):
            action = Action(
                title=obj["action"].get("title", ""),
                rows=[ActionRow(k=r["k"], v=r["v"]) for r in obj["action"].get("rows", [])],
            )

        sections = [
            SecondarySection(
                when=section["when"],
                trigger=section.get("trigger"),
                rows=[
                    SecondaryRow(text=row["text"], vp=row["vp"], or_=row.get("or", False))
                    for row in section.get("rows", [])
                ],
            )
            for section in obj.get("sections", [])
        ]
        return SecondaryMission(
            name=obj["name"],
            slug=slug,
            when_drawn=obj.get("whenDrawn"),
            action=action,
            sections=sections,
        )
    return None


def fetch_all_secondary_missions(session=None, *, delay: float = 0.3) -> list[SecondaryMission]:
    session = session or new_session()

    index_html = fetch(session, "/11th/secondary-missions")
    card_paths = extract_links(index_html, "/11th/secondary-missions/")

    missions: list[SecondaryMission] = []
    for card_path in card_paths:
        time.sleep(delay)
        card_html = fetch(session, card_path)
        slug = card_path.rsplit("/", 1)[-1]
        mission = parse_secondary_mission_page(card_html, slug)
        if mission is not None:
            missions.append(mission)
    return missions


def emit(missions: list[SecondaryMission], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "secondary-missions.json"
    out_path.write_text(json.dumps([asdict(m) for m in missions], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch 11th-edition secondary mission cards from gdmissions.app.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    missions = fetch_all_secondary_missions()
    out_path = emit(missions, args.output_dir)
    print(f"{out_path} ({len(missions)} missions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
