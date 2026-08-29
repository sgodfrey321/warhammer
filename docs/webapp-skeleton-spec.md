# Web app skeleton — build spec for Claude Code

## Architecture decision (made this session)
- **Backend**: FastAPI, pure JSON API — no server-rendered templates.
- **Frontend**: separate React app (Vite), calls the API. Two codebases in one repo (`backend/`, `frontend/`).
- **Storage**: SQLite for v1. Matches the plan's earlier decision to start per-device, no cross-device sync yet. Use SQLModel or SQLAlchemy — either is fine, pick based on whichever has better FastAPI-native ergonomics at build time.
- **Auth**: none for v1. Single local user, no accounts.

## Scope for this skeleton
Build the **v1 scope** from `docs/app-plan.md` — Roster Builder + Battle Tracker with phase checklist, Active Effects, and Unit Synergies. Do not attempt: sync, structured Mission/Primary/Secondary VP scoring, the Battlefield Photo module, or full rules-eligibility computation (surface warnings, don't hard-block — see app-plan.md's "eligibility is resolved, not hardcoded" section for why).

Read `docs/app-plan.md` in full before starting — it has the data model, the five-phase structure with sub-steps, and the reasoning behind each design choice. This spec only covers translating that into an actual API and DB schema; it doesn't repeat the "why."

## Data model → schema
Translate directly from `docs/app-plan.md`'s data model section:
- `Roster` (id, name, faction, battle_size, points_limit, detachments: list, created_at, updated_at)
- `Unit` (roster entry: id, roster_id FK, unit_definition_id FK, quantity, notes)
- `UnitDefinition` (id, faction, name, points_cost, keywords: list, source_catalogue_id, source_entry_id) — **populated by import, not created via the API**. See "Importing indexer output" below.
- `UnitSynergy` (id, roster_id FK, source_unit_id FK, target_unit_id FK, trigger_phase, note)
- `BattleSession` (id, started_at, roster_id FK nullable, battle_round, active_player, current_phase, players: [PlayerState])
- `PlayerState` (cp_gained, cp_spent, vp — embedded in BattleSession or its own table with a battle_session_id FK, either is fine)
- `ActiveEffect` (id, battle_session_id FK, label, owner_player, duration_type, created_at_step, lifts_restriction nullable)
- `UnitTurnState` (id, battle_session_id FK, unit_id FK, battle_round, turn_owner, move_type, has_shot, has_charged, has_fought, flags: list)

Keep `points_cost` on `UnitDefinition` as the MFM-sourced value (per the indexer spec) — don't let the app itself become a second source of truth for points.

## Importing indexer output
The BSData indexer (`tools/bsdata-indexer/`) produces per-faction JSON on disk, separately from this app. Write a one-time/re-runnable import script (`backend/scripts/import_unit_definitions.py` or similar) that:
1. Reads each faction's indexer output JSON.
2. Upserts into the `UnitDefinition` table, keyed by `source_entry_id` so re-running after a dataslate update updates existing rows rather than duplicating them.
3. Is run manually (`python -m scripts.import_unit_definitions`) after the indexer produces new output — not triggered automatically by the API at request time.

## API endpoints (sketch — adjust as you build, this is a starting shape not a contract)

**Rosters**
- `GET/POST /rosters`
- `GET/PATCH/DELETE /rosters/{id}`
- `POST /rosters/{id}/units`, `PATCH/DELETE /rosters/{id}/units/{unit_id}`
- `GET/POST /rosters/{id}/synergies`, `DELETE /rosters/{id}/synergies/{id}`

**Unit reference data (read-only, from import)**
- `GET /unit-definitions?faction=...&search=...` — powers the roster editor's "add unit" autocomplete

**Battles**
- `POST /battles` (optionally attach `roster_id`)
- `GET /battles/{id}`
- `PATCH /battles/{id}/advance-phase`
- `PATCH /battles/{id}/players/{n}` (cp_gained, cp_spent, vp adjustments)
- `POST /battles/{id}/effects`, `DELETE /battles/{id}/effects/{id}` (dismiss)
- `PATCH /battles/{id}/units/{unit_id}/turn-state` (move_type, has_shot, etc.)

## What "skeleton" means for this first pass
Not a feature-complete build. Enough to prove the shape end-to-end:
1. Create a roster, add a few units via the `UnitDefinition` autocomplete (using real imported Aeldari data — Hank's list is a good manual test case).
2. Start a battle attached to that roster.
3. Advance through all 5 phases of a turn, watching `current_phase` and `battle_round` update correctly (including the player-turn handoff and battle-round increment logic from the plan's phase model).
4. Log one Active Effect, watch it get flagged for dismissal at the correct phase/turn boundary (the Farseer "until your next Command phase" case from the plan is the right thing to test against, since it's the trickiest duration type — spans a full opponent turn).
5. Add one Unit Synergy to a roster, see it surface when a battle attached to that roster enters the matching phase.

If those five things work, the skeleton has proven the hard part (the state model), and everything after that is UI polish and more CRUD.

## Explicitly deferred (don't build yet)
- Any auth/multi-user concept.
- Structured Primary/Secondary Mission VP scoring (flagged in app-plan.md section 9 as still needing design — don't improvise a schema for it now).
- Battlefield Photo module (app-plan.md section 8, Want to Have).
- Full rules-eligibility computation — `UnitTurnState.move_type` should be tracked and a warning surfaced, not enforced/blocked.
