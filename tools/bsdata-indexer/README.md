# BSData Indexer

Builds the app's `UnitDefinition` reference data (faction, name, points, keywords) from
[BSData](https://github.com/BSData)'s community-maintained mirror of Games Workshop's
Warhammer 40,000 BattleScribe data, instead of hand-entering every unit. See `../../SPEC.md`
(the original build spec) and `../../app-plan.md` (the app's data model) for the surrounding
design.

## ⚠️ License caveat — read before using this beyond your own private reference

The BSData repos are **community-maintained mirrors of Games Workshop's copyrighted game
content** (unit names, points, rules text). "Community-maintained, not endorsed by GW"
protects the maintainers from a claim of endorsement — it does **not** by itself clear
redistribution rights for that content in a separate product. `wh40k-11e-mfm` carries an MIT
license on its own repo, but that covers the maintainers' tooling/structuring of the data, not
necessarily GW's underlying IP (the points values, unit names, and rules text itself).

**Before this indexer's output is used for anything beyond your own private reference —
before it ships in an app, gets redistributed, or is shown to anyone else — get an actual
license read on this**, not just this note. Whoever picks this back up: read that caveat
before extending this tool's scope.

## What this does

1. Fetches faction catalogue + shared Library JSON from
   [`BSData/wh40k-11e`](https://github.com/BSData/wh40k-11e) (a JSON mirror of the BattleScribe
   catalogue schema — same `entryLink`/`catalogueLink`/`targetId` structure as the `.cat` XML
   files, just JSON, so no XML parsing is needed).
2. Resolves every unit `entryLink` in a faction file against its linked Library catalogue to
   get keywords and a reference points value (catalogue points are **not** authoritative — see
   below).
   Each resolved unit also carries its own embedded stat-line (M/T/Sv/W/LD/OC, from the
   entry's `"Unit"`-typed profile) and abilities (name + description text, from its
   `"Abilities"`-typed profiles) — this is where things like a Warlock's "can be attached to
   Guardian Defenders / Storm Guardians / Warlock Conclave" leader text come from.
3. Cross-references each resolved unit's points against
   [`BSData/wh40k-11e-mfm`](https://github.com/BSData/wh40k-11e-mfm), the structured snapshot
   of the official Munitorum Field Manual. **MFM is the authoritative points source** —
   catalogue points can be stale.
4. Emits one JSON file per faction to `output/`, sorted and stable-keyed for git-diffable
   re-runs.

Units with no MFM match are still emitted (`mfm_matched: false`, empty `points`), not dropped —
gaps should be visible, not silent.

## Why points is a list of tiers, not a single number

The MFM data prices some units per squad size (`Guardian Defenders`: only sold as an 11-model
unit for 90pts) and some per "which copy of this unit in your list" (`Wave Serpent`: 115pts for
your 1st–3rd, 125pts for your 4th+). `UnitDefinition.points` is a list of
`{range, models, points, label}` tiers to represent that, not a flat `points_cost` int.

## MFM name matching is case-insensitive, on purpose

MFM title-cases every word in a unit name (`Daemon Prince Of Khorne With Wings`); catalogues
use natural sentence case (`Daemon Prince of Khorne with wings`). Found on World Eaters: this
silently broke matching for real, common, currently-priced units — Khârn the Betrayer and both
Daemon Prince variants all came back `mfm_matched: false` with no other symptom. (An accent in
"Khârn" looked like the likely culprit at first; it wasn't — both sides had it correctly, only
the connector-word casing differed.) `util.normalize_name()` casefolds both sides before the
join for exactly this reason — don't switch either side back to exact string comparison.

## The faction → MFM mapping isn't 1:1

Catalogue faction files and MFM per-faction yaml files don't line up one-to-one — e.g. most
Space Marine successor chapters (Iron Hands, Raven Guard, Salamanders, Ultramarines, White
Scars, Imperial Fists) have their own catalogue file but share the generic `space-marines.yaml`
MFM points, since they don't have enough unique units for their own points file. This mapping
lives in `bsdata_indexer/faction_map.py`, which is explicit about which pairs were actually
cross-checked against real data during this tool's initial build versus which were inferred
from name correspondence — see the module docstring. A wrong mapping shows up as a high
`mfm_matched: false` rate for that faction rather than silently wrong points, since MFM lookup
is by exact unit name.

## Synergy enrichment (`--enrich`, second stage)

Per `SPEC.md` (in this same directory — a separate, later addition from the root `SPEC.md`
above): a second pipeline stage that reads each unit's `abilities[].text` and extracts
**synergy candidates** — which keyword an ability's effect targets, when it triggers, how long
it lasts. Two tiers:

- **Tier 1** (`bsdata_indexer/enrichment/tier1.py`) — free, local, regex-based. Handles the
  `■ Trigger: ... ■ Effect: ...` templated abilities (Battle Focus-style) and `friendly
  ^^Keyword^^ unit`-marked auras/buffs. Declines (defers to Tier 2) rather than guessing
  whenever a match is ambiguous — e.g. two distinct keywords ORed together in one ability.
  On the real Aeldari - Craftworlds output: **59 of 215 abilities (27%) resolved at zero
  cost**, including the exact Farseer/Doom-style worked example from `app-plan.md` (Eldrad
  Ulthran's "Doom (Psychic)": `keyword=AELDARI, phase=movement, duration=until_next_command_phase`).
- **Tier 2** (`bsdata_indexer/enrichment/tier2.py`) — everything Tier 1 declines is sent to the
  Anthropic **Batches API** in one call per faction (async, 50% of standard per-token cost;
  structured JSON output via `output_config.format`, not tool use). Requires the optional
  `anthropic` package (`pip install -e .[enrich]`) and API credentials — **this costs real
  money**, which is why `--enrich` is opt-in and a plain build never triggers it.

**Caching**: no separate cache file — each faction's `output/<slug>-synergies.json` is itself
the memo table. Every record carries the `text_hash` it was computed from, so re-running only
resubmits abilities whose text actually changed since the last run (SPEC.md's "hash each
ability's text, skip Tier 2 for unchanged hashes," satisfied without a second store to keep in
sync with the first).

```bash
pip install -e ".[dev,enrich]"
python -m bsdata_indexer.cli --faction "Aeldari - Craftworlds" --enrich -v
```

Output is a separate artifact (`<slug>-synergies.json`), not merged back into the base
`<slug>.json` — per SPEC.md, since it's interpreted/extracted data rather than directly parsed,
and may need regenerating independently with a better prompt later.

**Known gaps**: Tier 1's keyword regex only catches `friendly ... unit/units/model/models`
phrasing (marked `^^like this^^`, or unmarked ALL-CAPS) — SPEC.md's other example phrasing
("friendly units with the ASPECT WARRIOR keyword") isn't matched and falls through to Tier 2,
which is the intended/safe behavior, just worth knowing when reading the tier1-vs-tier2 split.

## Usage

```bash
cd tools/bsdata-indexer
pip install -e .[dev]

python -m bsdata_indexer.cli --faction "Aeldari - Craftworlds" --faction "Chaos - World Eaters" -v
python -m bsdata_indexer.cli --all -v      # every faction with a known/derivable MFM mapping
python -m bsdata_indexer.cli --all --force-refetch -v   # ignore cache, re-download everything
```

Re-run whenever a dataslate or faction pack drops (roughly monthly). Unchanged upstream repos
are skipped via a cached commit-sha check (`cache/`, gitignored) — only `output/` is meant to
be committed, so you can review a real diff before deciding it looks right.

## Tests

```bash
pytest
```

Runs entirely against small hand-trimmed fixtures in `tests/fixtures/` — no network needed.

## Known gaps (v1)

- **Squad stats now resolve for every Aeldari unit checked (102/102)** — was 68/104 originally,
  36 empty. Two distinct gaps, both fixed:
  - A squad's own catalogue entry usually has no top-level `"Unit"` profile — the base model's
    stat line lives one level down, in a nested `selectionEntry` (either directly under the
    entry's own `selectionEntries`, e.g. Guardian Defenders → "Guardian Defender", or inside
    `selectionEntryGroups[].selectionEntries`, e.g. Dire Avengers → group "4-9 Dire Avengers" →
    "Dire Avenger"). `catalogue._nested_unit_stats()` handles both shapes, taking the first
    nested model with a stat line as the squad's baseline (the rank-and-file model is listed
    before upgrade options like an Exarch in every case checked).
  - Some entries (nested or top-level) don't embed a `"Unit"` profile at all — they reference
    one in the catalogue's separate `sharedProfiles` pool via `infoLinks[type == "profile"]`
    instead. Confirmed on Windriders (each weapon-loadout variant links to one shared
    "Windriders" profile) and Warlock (a single-model entry linking directly, no nesting
    involved). `catalogue._info_link_stats()` resolves this, backed by a `build_profile_index()`
    merged the same way as the existing library entry index.
  - Both are heuristics/best-effort against real data actually inspected, not schema
    guarantees — a future faction could still use a shape not yet seen. Check a faction's
    output for `"stats": {}` before trusting a unit's stat line is populated.
- **Weapon profiles now populate `UnitDefinition.weapons`** — `catalogue._weapon_profiles()`
  recursively collects every `"Ranged Weapons"`/`"Melee Weapons"`-typed profile reachable from
  a unit's own subtree (embedded directly, via `entryLinks`, or via `infoLinks` into
  `sharedProfiles` — the same three resolution paths as the stats fix above), deduped by
  weapon name. This is deliberately the *set of weapons a unit is associated with* (a Dire
  Avenger squad's Exarch options — Diresword, Power Glaive — all show up together), not a
  chosen loadout; a specific roster's actual equipped weapons are separate, roster-instance
  data (see `backend/app/battlescribe_import.py`'s `ParsedEntry.loadout`). Real coverage:
  95/102 Aeldari, 58/64 World Eaters units got at least one weapon; the remaining ~7% (mostly
  named Crucible-of-Battle/narrative cards and a couple of Character entries) use some other
  shape not yet identified — same caveat as the stats heuristics above.
- Two catalogue-config entries per faction (roughly) resolve to real targets but aren't actual
  units — a `"Detachment"` picker, a `"Battle Focus - Agile Manoeuvres"`-style faction rule —
  and were leaking into `units[]` looking like empty, unmatched real units. Fixed by checking
  the resolved target's own `type` field (must be `"unit"` or `"model"`, not `"upgrade"`) —
  see `resolve_faction`'s docstring for how this was confirmed against real data.
- Abilities only capture what's embedded directly on the unit's own entry. Universal/core rules
  referenced via `infoLinks` (e.g. Wraithlord's "Feel No Pain" — a `type: "rule"` link, not an
  embedded profile) aren't resolved: they live in the `sharedRules` pool, and for the units
  checked so far that pool was empty at the faction-Library level, so those rules are likely
  defined in the `.gst` game system file (`Warhammer 40,000.json`), which isn't fetched at all
  currently. Follow-up work, not done here.
- `faction_map.py`'s unverified entries (see above) haven't been checked unit-by-unit.
- Not every faction resolves cleanly yet. World Eaters (checked directly) needed both its own
  inline `sharedSelectionEntries` *and* the external library index merged together — some other
  faction may need something not yet seen. Check a faction's `unresolved_entrylinks` count in
  its output before trusting it's complete.
