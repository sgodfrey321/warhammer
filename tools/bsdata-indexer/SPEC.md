# Synergy enrichment — build spec for Claude Code

## Context
The base indexer (see `tools/bsdata-indexer/SPEC.md`) produces per-faction `UnitDefinition` records with `abilities: [{name, text}]`. This step reads that ability text and extracts **synergy candidates** — cases where one unit's ability affects other units sharing a keyword. It runs *after* the indexer, as a second pipeline stage, not a live app feature.

**This is a batch enrichment job, not an agent.** No tool-calling loop, no autonomous decisions. It's: read some text, ask Claude to extract structure from it, save the result. Runs offline, on a schedule tied to data updates, same as the indexer itself.

## Why keyword-matching, not unit-naming
Checked against the real Farseer ability text: it says "each time a **friendly Aeldari model** makes an attack that targets that enemy unit" — it never names Dire Avengers or any specific unit. This is the normal pattern for GW's ability text: conditions are phrased as keywords ("AELDARI," "ASPECT WARRIOR," "WORLD EATERS CHARACTER excluding EPIC HERO"), not named units. So the real task is: **for each ability, extract which keyword(s) it cares about** — then matching that against a specific roster's actual units is a separate, simple lookup (roster unit keywords ∩ ability's target keyword), not something that needs re-extracting per roster.

## Two-tier extraction

**Tier 1 — deterministic, no LLM.** Many abilities follow templated phrasing closely enough for regex/string matching to extract:
- The target keyword(s) (e.g. "friendly AELDARI models", "friendly units with the ASPECT WARRIOR keyword")
- The trigger phase, when explicitly named ("Your Shooting phase", "your opponent's Movement phase")
- The duration phrase ("until the end of the phase", "until the end of the turn", "until the start of your next Command phase")

Run this first. Cheap, deterministic, testable, no API cost. Expect it to cleanly handle a meaningful fraction of abilities — probably the majority, given how consistent GW's templated language is.

**Tier 2 — LLM batch extraction, for what Tier 1 can't parse cleanly.** For ability text that doesn't match the regex patterns (irregular phrasing, multi-clause conditions, exclusions like "excluding EPIC HERO units," compound triggers), send the ability text to Claude via the API and ask for the same structured shape:
```json
{
  "ability_name": "...",
  "affects_keyword": "AELDARI" | "ASPECT_WARRIOR" | null,
  "affects_exclusions": ["EPIC_HERO"] | [],
  "trigger_phase": "shooting" | "movement" | "command" | "charge" | "fight" | "any" | null,
  "trigger_detail": "short paraphrase of the trigger condition",
  "duration_type": "end_of_phase" | "end_of_turn" | "end_of_battle_round" | "until_next_command_phase" | "until_condition_clears" | "manual" | null,
  "confidence": "high" | "low"
}
```
Mark anything the model itself flags as uncertain (`confidence: low`, or a null field it couldn't extract) for manual review rather than trusting it silently — same principle as the indexer's `mfm_matched: false` handling.

## Pipeline behavior
- **Trigger**: run automatically whenever the base indexer's output changes for a faction — not on a separate schedule, not manually invoked each time. Chain it: indexer runs → diff detected → enrichment runs on the changed/new abilities only.
- **Caching**: hash each ability's `text` field. Skip Tier 2 (the paid API call) for any ability whose text hash matches a previous run — most abilities don't change between dataslates, no reason to re-spend on them.
- **Output**: one enrichment record per ability, keyed by the same `source_entry_id` used in the indexer output, so it joins cleanly. Not merged back into the base `UnitDefinition` file — keep it a separate artifact, since it's a different kind of data (interpreted/extracted vs. directly parsed) and you may want to regenerate it independently later with a better prompt.

## What this does NOT do (by design)
- **Does not auto-create `UnitSynergy` records.** A keyword match tells you "these units *could* interact" — with a keyword as broad as "AELDARI," that could be nearly every unit in a Craftworlds list, which is noise, not a useful reminder. The app should show **candidates** (a specific ability + the roster's units that match its target keyword) and let the person building the roster decide which pairings are actually worth a standing reminder. The judgment call of "do I personally want to be reminded about this" stays with the user.
- **Does not consider the opponent's roster.** Some abilities' triggers/targets could in principle reference enemy keywords (e.g. "attacks that target a MONSTER or VEHICLE unit"), which would need visibility into what the opponent is fielding to fully resolve. That's a separate, larger feature (an opponent-roster data model doesn't exist yet) — explicitly out of scope here. This enrichment step only reasons about the ability text and the *owning* roster's own units.
- **Does not run live during a battle.** This is a pre-battle, data-pipeline step. By the time someone's using the Battle Tracker, synergy candidates should already be reviewed and either accepted (became a `UnitSynergy`) or dismissed.

## Connecting back to the app
When a person builds a roster and the enrichment data is available, the Roster Editor can show: "Farseer Skyrunner's [ability] could affect: Dire Avengers, Fire Dragons, Howling Banshees, Striking Scorpions ×2, Warp Spiders (all share the AELDARI keyword)." They pick the one(s) that actually matter to their play (e.g. just Dire Avengers), and that selection becomes a `UnitSynergy` record — pre-filled with the `trigger_phase` the enrichment already extracted, so accepting a candidate is close to one tap, not a form to fill out from scratch.
