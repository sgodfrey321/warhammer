# gdmissions fetchers

Fetches 11th-edition Primary Mission, Secondary Mission, and deployment Layout data from
[gdmissions.app](https://gdmissions.app) — a fan-made Warhammer 40,000 companion site, not
BSData and not Games Workshop. Kept separate from `tools/bsdata-indexer` since it's a different
upstream source with a different shape. Wired into the app: `backend/app/routers/
{primary_missions,secondary_missions,layouts}.py` each read one of this tool's output files
straight off disk (no DB table), powering the frontend's `/missions` page and the Battle Setup
flow.

**License note**: the mission text itself is derived from Games Workshop's copyrighted rules,
repackaged by a fan site. Treat the output the same way as `tools/bsdata-indexer`'s — a
private/personal reference, not something to redistribute.

## How it works

Each page's data (mission mechanics, layout image URLs) is server-rendered as clean JSON
directly into the page's initial HTML — inside a Next.js RSC "flight" payload script tag
(`self.__next_f.push([n, "..."])`), not a documented public API, but a plain HTTP GET + parse
is enough; no headless browser or JS execution needed. Confirmed directly: `robots.txt`
explicitly allows crawlers, naming `ClaudeBot`/`Anthropic-AI` among others. Shared parsing
helpers (`_shared.py`) are used by all three fetchers below — notably
`extract_object_with_key()`, which scans backward from a target key to find the JSON object
that actually *encloses* it, tracking bracket depth rather than naively taking the nearest `{`
before it (a naive scan breaks as soon as a complete nested object sits between the enclosing
object's other fields and the target key — a real bug hit on Secondary Missions, where an
`"action": {"rows": [{...}, {...}]}` block sits before `"sections"` in the same object).

## `fetch_missions.py` — Primary Missions

```bash
cd tools/gdmissions
../../.venv/Scripts/python.exe fetch_missions.py
```

Crawls the deck index → each of the 5 decks' listings → each of their 5 cards (25 pages, plus 6
listing pages) and writes `output/primary-missions.json`. Each mission carries `deck`/`vs` (the
Force Disposition matchup) and `sections[].tiers[]` (`when`/`trigger` + scoring tiers, some with
`per_unit`/`cumulative` flags). The full 5×5 Force Disposition Matrix is entirely derivable from
this one file (group by `deck`/`vs`) — no separate matrix scrape needed.

## `fetch_secondary_missions.py` — Secondary Missions

```bash
../../.venv/Scripts/python.exe fetch_secondary_missions.py
```

Crawls `/11th/secondary-missions` (a flat list, not deck-organized — 18 real cards) and writes
`output/secondary-missions.json`. Meaningfully different shape from Primary Missions: an
optional `action` block (a Battlefield Action — title + `rows` of `{k, v}` like STARTS/UNITS/
USE LIMIT/COMPLETES/EFFECT), an optional `when_drawn` instruction (some cards have one, some the
other, some both, some neither — every field kept optional rather than assumed present), and
`sections[].rows[]` (not `tiers[]`) where `vp` is a **string** (`"3"`, not `3`) and uses an `or`
flag instead of `cumulative`/`per_unit`. Text uses HTML tags (`<b>`, `<span class="cB__mark">`)
instead of Primary Missions' `**bold**`/`^^keyword^^` markdown.

## `fetch_layouts.py` — Deployment Layouts

```bash
../../.venv/Scripts/python.exe fetch_layouts.py
```

Crawls `/11th/layouts` → 5 deck pages → 25 matchup pages (31 pages total) and writes
`output/layouts.json`. Each matchup lists 2–3 layout images, each with both a `no-measurements`
and `with-measurements` variant — stored as full `https://gdmissions.app/...` URLs so the
frontend can hotlink gdmissions.app's own hosted images directly rather than mirroring them.

## Tests

```bash
../../.venv/Scripts/python.exe -m pytest tests/
```

Parsing logic only, against saved fixture HTML — no live network calls in tests. One fixture
pair per real shape variant found (e.g. Secondary Missions' Cleanse/Beacon fixtures cover the
action-block vs. when-drawn-only cases).
