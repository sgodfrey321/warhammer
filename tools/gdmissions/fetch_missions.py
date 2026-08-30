"""Fetches 11th-edition primary mission deck data from gdmissions.app -- a fan-made
Warhammer 40k companion site, not BSData/GW. Confirmed directly: `robots.txt` explicitly
allows crawlers (including Claude/Anthropic-AI by name), and each mission card's full
mechanics (trigger conditions, VP values, per-unit/cumulative flags) are server-rendered as
clean JSON straight into the page's initial HTML -- inside a Next.js RSC "flight" payload
script tag (`self.__next_f.push([n, "..."])`), not a documented public API, but a plain
HTTP GET + parse is enough; no headless browser or JS execution needed.

Like BSData's unit data, the mission text itself is derived from GW's copyrighted rules,
just repackaged by a fan site -- treat this output as a private/personal reference the same
way, not something to redistribute.

Usage: python fetch_missions.py [--output-dir PATH]
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
class MissionTier:
    text: str
    vp: int
    per_unit: bool = False
    cumulative: bool = False
    kind: str | None = None  # e.g. "eob" (end-of-battle) -- confirmed on real data


@dataclass(frozen=True)
class MissionSection:
    when: str
    # "END OF BATTLE" sections carry no "trigger" text at all (confirmed on real data,
    # e.g. Inescapable Dominion) -- they have a "headerKind" instead. Both optional so
    # neither shape is forced into the other.
    trigger: str | None = None
    header_kind: str | None = None
    tiers: list[MissionTier] = field(default_factory=list)


@dataclass(frozen=True)
class Mission:
    name: str
    deck: str
    vs: str
    sections: list[MissionSection] = field(default_factory=list)


def parse_mission_page(html: str) -> Mission | None:
    """Extracts a mission card's {name, deck, vs, sections} object from a card detail
    page's server-rendered flight payload. Returns None if the page doesn't look like a
    mission detail page (e.g. a deck listing page instead has no "sections" key at all)."""
    for payload in iter_push_payloads(html):
        obj = extract_object_with_key(payload, "sections")
        if obj is None or "name" not in obj:
            continue
        sections = [
            MissionSection(
                when=section["when"],
                trigger=section.get("trigger"),
                header_kind=section.get("headerKind"),
                tiers=[
                    MissionTier(
                        text=tier["text"],
                        vp=tier["vp"],
                        per_unit=tier.get("perUnit", False),
                        cumulative=tier.get("cumulative", False),
                        kind=tier.get("kind"),
                    )
                    for tier in section.get("tiers", [])
                ],
            )
            for section in obj.get("sections", [])
        ]
        return Mission(name=obj["name"], deck=obj["deck"], vs=obj["vs"], sections=sections)
    return None


def fetch_all_primary_missions(session=None, *, delay: float = 0.3) -> list[Mission]:
    """Crawls the deck index -> each deck's listing -> each card's detail page. Delay is a
    small politeness pause between requests (25 pages total: 1 index + 5 decks + 5x5 cards)."""
    session = session or new_session()

    index_html = fetch(session, "/11th/primary-missions")
    deck_paths = extract_links(index_html, "/11th/primary-missions/")

    missions: list[Mission] = []
    for deck_path in deck_paths:
        time.sleep(delay)
        deck_html = fetch(session, deck_path)
        card_paths = extract_links(deck_html, f"{deck_path}/")
        for card_path in card_paths:
            time.sleep(delay)
            card_html = fetch(session, card_path)
            mission = parse_mission_page(card_html)
            if mission is not None:
                missions.append(mission)
    return missions


def emit(missions: list[Mission], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "primary-missions.json"
    out_path.write_text(json.dumps([asdict(m) for m in missions], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch 11th-edition primary mission decks from gdmissions.app.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    missions = fetch_all_primary_missions()
    out_path = emit(missions, args.output_dir)
    print(f"{out_path} ({len(missions)} missions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
