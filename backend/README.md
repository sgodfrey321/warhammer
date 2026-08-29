# Backend (PoC)

FastAPI + SQLite implementation of `docs/webapp-skeleton-spec.md` and
`docs/battle-engine-spec.md`. Pairs with `../frontend` (React + Vite) — see that
directory's README to run both together. CORS is enabled for `localhost:5173`/`5174`
(Vite's default dev ports) only; add more origins in `app/main.py` if you serve the
frontend elsewhere.

## Setup

Reuses the repo's root `.venv` (no separate backend venv):

```bash
cd G:/PycharmProjects/warhammer-manager
.venv/Scripts/python.exe -m pip install -e "backend[dev]"
```

## Import unit reference data

Populates `UnitDefinition` — stats, abilities, and weapon profiles — from the
bsdata-indexer's output (`tools/bsdata-indexer/output/*.json`). Safe to re-run after a
dataslate update — upserts by `source_entry_id`.

```bash
cd backend
../.venv/Scripts/python.exe -m scripts.import_unit_definitions
```

**Simplification**: the indexer emits a list of points *tiers* (squad-size / copy-number
pricing, e.g. Wave Serpent 115pts for your 1st–3rd, 125pts for your 4th+).
`UnitDefinition.points_cost` here is a flat int — the first tier's value. Multi-tier
pricing isn't modeled yet; revisit if/when that distinction matters for the roster
builder UI.

## Run it

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Interactive API docs at `http://127.0.0.1:8000/docs`. Or use `../dev.py` from the repo
root to start this and the frontend together.

## Persistence

Every roster, unit, attachment, synergy, pool, and battle (including in-progress turn
state) is written straight to `backend/warhammer.db` (SQLite) on every change — nothing
is ever held only in memory. Restarting the server, the browser, or your machine loses
nothing; the data is exactly as you left it. `GET /battles?roster_id=X` (surfaced in the
Roster Editor as "Previous battles") is how you get back to a battle you started earlier
instead of needing to remember its URL.

For a second, throwaway instance (testing, a scratch roster you don't want mixed into
your real one) set `WARHAMMER_DB_PATH` before starting the server to point it at a
different file instead of the default:

```bash
WARHAMMER_DB_PATH=/tmp/scratch.db ../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

## What's here

**Roster Builder** (`app/routers/rosters.py`)
- `Roster` CRUD, plus `POST /rosters/import` — parses a BattleScribe/NewRecruit roster
  export (`app/battlescribe_import.py`) and creates the roster's `Unit` rows, matching
  each selection against `UnitDefinition` by catalogue id. Also extracts, from the same
  file: **leader/bodyguard attachments** (`UnitAttachment`, from the export's
  `incomingAssociations`) and each unit's **actual equipped loadout**
  (`Unit.loadout` — weapon name + count, aggregated from the export's nested
  model-group/wargear selections, not just "what the unit could carry").
- `Unit` CRUD (roster entries) — manually-added units get an empty `loadout: []` (only
  import populates it; the Battle Tracker falls back to showing `UnitDefinition.weapons`
  as reference options in that case).
- `UnitAttachment` CRUD — a Character leading a bodyguard unit; the pair acts as one
  combined unit in the Battle Tracker (shared turn-state controls).
- `UnitSynergy` CRUD — roster-level "activate A before B" reminders, surfaced in the
  Battle Tracker during their `trigger_phase`.
- `DeclaredStatePool` CRUD — round/turn/phase-scoped resource pools (Battle Focus
  tokens, Blessings of Khorne), stacking or non-stacking; not auto-populated from
  anything yet, see `docs/TODO.md`.

**Battle Tracker** (`app/routers/battles.py`, `app/phases.py`)
- `POST/GET /battles`, `GET /battles?roster_id=X` (list, most recent first),
  `PATCH /battles/{id}/advance-phase` — the phase/turn/round engine, see below.
- `PATCH /battles/{id}/players/{n}` — CP/VP tracking (Core CP auto-granted both players
  every Command phase, on top of manual adjustments).
- `POST/DELETE /battles/{id}/effects[/{id}]` — `ActiveEffect`s with computed `expired`
  (never auto-deleted; the person confirms dismissal).
- `POST /battles/{id}/synergies/{id}/acknowledge` — dismisses a synergy reminder for the
  current phase instance only; reappears next time that phase is entered.
- `POST /battles/{id}/pools/{id}/spend|add` — spend a non-stacking pool (active player)
  or add a stacking-pool entry; both refill/clear automatically at the right
  phase/turn/round boundary via `advance-phase`.
- `PATCH /battles/{id}/units/{unit_id}/turn-state` — per-unit move/shot/charge/fight
  tracking, with a computed non-blocking `eligibility_warning` (e.g. Advanced this turn
  → can't shoot) — surfaced, never enforced.

## Tests

```bash
cd backend
../.venv/Scripts/python.exe -m pytest
```

32 tests, in-memory SQLite, no network. Beyond CRUD: the full phase/round/turn-handoff
sequence and `until_next_command_phase` effect expiry (the Farseer "Doom" scenario,
surviving a full opponent turn), `DeclaredStatePool` refill/clear timing, synergy
reappearance, `UnitAttachment` parsing/cleanup against the real committed
`docs/Hank 2k.json` export, and weapon-loadout aggregation (including the single-model
vs. multi-model-squad shape difference in the export).

All of the above have also been driven live against a running `uvicorn` server with
real imported data — not just the test suite.

## Design notes

- **`global_step`**: `BattleSession` stores one monotonic int, incremented once per
  `advance-phase` call. `current_phase`, `active_player`, `battle_round`, and the
  transition classification (`phases.transition_type` — phase/turn/round end) are all
  derived from it rather than stored — they can't drift out of sync.
- **`ActiveEffect.expired`**: computed at read time from `duration_type` +
  `created_at_step`, never auto-deleted. Matches the app's "surface consequences, don't
  enforce them" philosophy — dismissal is still the explicit `DELETE .../effects/{id}`.
  `end_of_turn` and `until_next_command_phase` are both owner-player-relative, not just
  "any boundary crossed" (a real bug, found and fixed: `end_of_turn` wasn't originally
  owner-relative).
- **`DeclaredStatePool`**: definition (roster-scoped, like `UnitSynergy`) separate from
  runtime state (`DeclaredStatePoolState` for non-stacking, `DeclaredStatePoolEntry` for
  stacking — a list of instances, not a single counter, since Blessings-of-Khorne-style
  pools accumulate rather than deplete). A pool starts full the first time it's
  referenced in a battle, not at zero.
- **`docs/app-plan.md`**, which `docs/webapp-skeleton-spec.md` says to read for full
  context, isn't actually present in this repo — only `webapp-skeleton-spec.md`,
  `battle-engine-spec.md`, and `SESSION-SUMMARY.md` exist under `docs/`. Built from
  those directly; flag if `app-plan.md` should be added back.
