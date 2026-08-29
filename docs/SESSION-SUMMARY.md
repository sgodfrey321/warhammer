# Session summary — Warhammer 40k tracker, planning session (28 Aug 2026)

This is a continuity document, not the plan itself. Read this first to get oriented, then go to the linked documents for detail.

## Documents produced this session

| File | What it is |
|---|---|
| `docs/app-plan.md` | The main app plan — data model, phase-by-phase battle tracker design, scope ladder, roster builder, all corrections and refinements made live during mockup review |
| `tools/bsdata-indexer/SPEC.md` | Build spec for the indexer that turns BSData's BattleScribe catalogues + MFM points snapshots into clean `UnitDefinition` JSON |
| `tools/synergy-enrichment/SPEC.md` | Build spec for the second-stage pipeline that extracts synergy *candidates* from ability text (keyword-matching + batch LLM extraction), chained after the indexer |
| `docs/webapp-skeleton-spec.md` | Architecture decision + build spec for the actual app: FastAPI (pure JSON API) + separate React frontend, SQLite for v1, no auth. Defines a narrow "skeleton means these 5 things work end-to-end" scope rather than full v1. |

The indexer is confirmed running (per your last message) — its output for Aeldari and World Eaters was reviewed directly in this session (see below).

## What this session actually did, roughly in order

1. **Established the core app shape**: two connected modules — Roster Builder (persistent) and Battle Tracker (live session state) — sharing one data model.
2. **Solved the points-database question in stages** rather than blocking on it: manual entry first, `UnitDefinition` reference table later. This later got real teeth (see Data pipeline below).
3. **Designed the battle-flow skeleton** against the actual current core rules (fetched and read directly, not assumed): 5 phases per turn, Command/Movement/Shooting/Charge/Fight, each with sub-steps.
4. **Built three mechanisms for the actual pain point** (buffs and ordering, the reason this app exists):
   - **Phase checklist** — predictable start/end-of-phase triggers.
   - **Active Effects** — anything with a duration, flagged when its boundary passes (validated against a real Aeldari Farseer ability with a multi-phase, cross-turn duration).
   - **Unit Synergies** — roster-level "activate A before B" reminders, surfaced when entering the relevant phase.
5. **Corrected two real modeling mistakes, caught during mockup review, not assumed away**:
   - Treated a two-detachment roster as a data conflict — wrong. 11th edition allows multiple detachments under a Detachment Points budget (confirmed against Warhammer Community's army-building article). Roster model changed from single `detachment` to `detachments: [{name, dp}]`.
   - Color-coded Khârn the Betrayer and Lord Invocatus as eligible for Vessels of Wrath's Character buff — wrong, they're Epic Heroes and the ability explicitly excludes Epic Heroes. Caught by querying real keyword data, not by re-reading the rules text carefully enough the first time.
6. **Extended the state model against two very different factions** (Aeldari: clean, token-economy, tactical; World Eaters: melee-focused, random/stacking buffs) to confirm it generalizes — added a scope ladder (battle → battle round → turn → phase → activation) and distinguished declared state (chosen, has a window) from derived state (accumulates from actions, constrains later phases).
7. **Found and validated a real data source**: `BSData/wh40k-11e` (BattleScribe catalogues) + `BSData/wh40k-11e-mfm` (points snapshots). Confirmed by direct inspection that catalogue IDs match a real NewRecruit roster export exactly. Found the catalogue's embedded points can be stale (Wraithlord: 130 in the raw catalogue vs. 125 actual current value) — this is why the indexer must treat MFM as authoritative, not the catalogue.
8. **Reviewed actual indexer output for two factions** (uploaded by you): Aeldari matched cleanly (96/104 units), World Eaters had a much worse match rate (25/66) with some real current units failing to match MFM (Khârn, Daemon Prince of Khorne) — logged as a named risk in the indexer spec, not silently ignored. You mentioned this is now fixed.
9. **Worked out the synergy-detection problem**: real ability text targets keywords ("friendly AELDARI models"), not named units — so this is a keyword-matching problem with an LLM fallback for irregular phrasing, not something requiring an autonomous agent. Explicitly scoped as a batch/offline pipeline stage, not a live app feature, and explicitly does NOT auto-create synergies — it produces candidates for a human to accept or dismiss.
10. **Flagged, deliberately not solved**: opponent-roster visibility (needed for any ability that keys off enemy unit keywords) — named as a real future question, kept out of scope.
11. **Covered the practical mechanics of running Tier 2** (LLM batch extraction): needs a separate Claude Console API key (distinct from any Claude.ai subscription), billed per token, Haiku + Batch API is the right cost-minimizing choice for this specific job, cost is real but likely small for this data volume.

## Mockups built during this session (all inline visualizations, not files)

Walked the full battle-tracker loop at least once, using real roster data throughout:
- Roster List (dashboard) — showed an over-limit warning state and an in-progress-battle resume banner
- Roster Editor — built twice: once with placeholder data, then rebuilt with Hank's real 1990pt Aeldari list (synergy row for Farseer/Dire Avengers), then again for World Eaters (corrected detachment display, corrected Epic Hero exclusion)
- Command phase — Battle Focus token pool, CP split into Gained/Spent, an effect expiring exactly on schedule
- Movement phase — rebuilt twice: once generic, once with real ability text and a real stat strip (M/T/Sv/InSv/W/LD) pulled from indexed data; then extended to show the full unit-selection list with a stable roster-order + quiet synergy-source tag design (deliberately not sorting units by relevance — see decision below)
- Shooting phase — synergy reminder + Active Effects list (original v1, still valid)
- Charge phase — conditional declared choice, end-of-phase trigger populated into the existing checklist slot
- Fight phase — stacking random declared state (Blessings of Khorne), per-enemy reactive trigger, activation-scoped declared choice

## Decisions worth remembering (easy to lose in a long thread)

- **Unit lists don't reorder for relevance.** Stable order (roster order), synergy sources get a small permanent icon tag, not a position change. Reordering caused by the player's own action (moving a unit) is fine; reordering caused by the app deciding something is "more important" is disorienting.
- **Moved units stay in place, dimmed** — not moved to a separate "done" list. Explicitly flagged as a real UX choice, not a forced default; revisit if it doesn't feel right at the table.
- **A synergy "icon tag" (always visible) and a phase-relevant "act now" banner are different UI languages** — don't conflate a quiet reminder with an urgent one.
- **The app is a bookkeeping/reminder tool, not a rules engine.** It surfaces consequences (e.g. "this unit Advanced, it normally can't shoot") rather than enforcing or computing them — the person always has the final say, especially for mitigations the app doesn't know about.

## Open threads, not yet resolved

- Fight phase's Fights-First alternating-activation sequence — flagged early as "the odd one out," never actually deep-dived.
- Battlefield Photo module (position plotting + unit ID via photo) — stays in "Want to Have," untouched since first scoped.
- Opponent-roster data model — needed for any enemy-keyword-conditioned ability, explicitly deferred.
- License terms for BSData usage — flagged repeatedly as a blocking legal question, never actually resolved (needs a human legal check, not something determinable in-chat).
- Roster Editor UI for reviewing/accepting synergy candidates once the enrichment pipeline produces them — designed conceptually, not mocked up.
- Mission/Primary/Secondary VP structure (from the reference-app screenshots early in the session) — logged as a needed data model addition, not yet designed in detail.

## Suggested next session starting point

Given the indexer and enrichment pipeline are now the active work (in Claude Code, on your local repo), the natural next chat-side task is either: (a) mock up the Roster Editor's synergy-candidate review UI once real enrichment output exists, or (b) tackle the Fight phase's alternating-activation sequence, which is the most mechanically complex phase and still under-designed relative to the others.
