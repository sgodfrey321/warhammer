"""Fetches 11th-edition deployment layout diagrams from gdmissions.app -- see
fetch_missions.py for the shared fetch/parse approach (same site, same Next.js
flight-payload trick).

Layouts are organized the same way as the Force Disposition Matrix (deck-vs-deck, 25
matchups: 5 deck index pages x 5 opponent matchups each), but unlike primary/secondary
missions the payload is **image assets**, not rules text -- each matchup page's flight
payload carries an object with "home"/"opponent" (the two dispositions) and a "layouts"
array of {number, name, image, measurementsImage}, where "image" is the no-measurements
PNG and "measurementsImage" is the with-measurements variant of the same diagram
(confirmed live on take-and-hold-vs-purge-the-foe: 3 layouts, each with both variants).

Scope stays light here: capture the image URLs per matchup as full https://gdmissions.app/...
URLs so the frontend can hotlink gdmissions.app's own hosted images directly -- we don't
mirror/host the images ourselves.

Like fetch_missions.py: this is a fan site, not GW/BSData, and the layouts are still fan
reinterpretations of GW's rules content -- personal reference only.

Usage: python fetch_layouts.py [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _shared import BASE_URL, extract_links, extract_object_with_key, fetch, iter_push_payloads, new_session

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class Layout:
    number: int
    name: str
    image: str
    measurements_image: str


@dataclass(frozen=True)
class LayoutMatchup:
    deck: str
    vs: str
    name: str
    layouts: list[Layout] = field(default_factory=list)


def _absolute(path: str) -> str:
    return path if path.startswith("http") else f"{BASE_URL}{path}"


def parse_layout_page(html: str, deck: str, vs: str) -> LayoutMatchup | None:
    """Extracts a matchup's {home, opponent, name, layouts} object from a layout detail
    page's server-rendered flight payload. Returns None if the page doesn't carry a
    "layouts" key at all (e.g. a deck listing page instead)."""
    for payload in iter_push_payloads(html):
        obj = extract_object_with_key(payload, "layouts")
        if obj is None or "name" not in obj:
            continue
        layouts = [
            Layout(
                number=layout["number"],
                name=layout["name"],
                image=_absolute(layout["image"]),
                measurements_image=_absolute(layout["measurementsImage"]),
            )
            for layout in obj.get("layouts", [])
        ]
        return LayoutMatchup(deck=deck, vs=vs, name=obj["name"], layouts=layouts)
    return None


def fetch_all_layouts(session=None, *, delay: float = 0.3) -> list[LayoutMatchup]:
    """Crawls the deck index -> each deck's listing -> each matchup's detail page (31 pages
    total: 1 index + 5 decks + 5x5 matchups)."""
    session = session or new_session()

    index_html = fetch(session, "/11th/layouts")
    deck_paths = extract_links(index_html, "/11th/layouts/")

    matchups: list[LayoutMatchup] = []
    for deck_path in deck_paths:
        time.sleep(delay)
        deck = deck_path.rsplit("/", 1)[-1]
        deck_html = fetch(session, deck_path)
        matchup_paths = extract_links(deck_html, f"{deck_path}/")
        for matchup_path in matchup_paths:
            time.sleep(delay)
            vs = matchup_path.rsplit("/", 1)[-1]
            matchup_html = fetch(session, matchup_path)
            matchup = parse_layout_page(matchup_html, deck, vs)
            if matchup is not None:
                matchups.append(matchup)
    return matchups


def emit(matchups: list[LayoutMatchup], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "layouts.json"
    out_path.write_text(json.dumps([asdict(m) for m in matchups], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch 11th-edition deployment layout diagrams from gdmissions.app.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    matchups = fetch_all_layouts()
    out_path = emit(matchups, args.output_dir)
    print(f"{out_path} ({len(matchups)} matchups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
