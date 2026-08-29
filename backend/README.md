# Backend (PoC)

FastAPI + SQLite implementation of `docs/webapp-skeleton-spec.md`. Pairs with
`../frontend` (React + Vite) — see that directory's README to run both together.
CORS is enabled for `localhost:5173`/`5174` (Vite's default dev ports) only; add
more origins in `app/main.py` if you serve the frontend elsewhere.

## Setup

Reuses the repo's root `.venv` (no separate backend venv):

```bash
cd G:/PycharmProjects/warhammer-manager
.venv/Scripts/python.exe -m pip install -e "backend[dev]"
```

## Import unit reference data

Populates `UnitDefinition` from the bsdata-indexer's output
(`tools/bsdata-indexer/output/*.json`). Safe to re-run after a dataslate update —
upserts by `source_entry_id`.

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

Interactive API docs at `http://127.0.0.1:8000/docs`.

## Tests

```bash
cd backend
../.venv/Scripts/python.exe -m pytest
```

12 tests, in-memory SQLite, no network. Covers roster/unit CRUD, unit-definition
search, importing the real committed `tools/bsdata-indexer/output/aeldari-craftworlds.json`
(twice, to check the upsert is idempotent), and the battle state machine — including
the trickiest case, an `until_next_command_phase` effect (the Farseer "Doom" scenario)
surviving a full opponent turn before expiring on schedule.

All 5 of the spec's "skeleton means these things work" scenarios were also driven live
against a running `uvicorn` server with real imported Aeldari data (roster creation,
battle start, a full 10-step phase/round/turn-handoff sequence, the cross-turn effect
expiry, and synergy surfacing scoped to its trigger phase) — not just the test suite.

## Design notes

- **`global_step`**: `BattleSession` stores one monotonic int, incremented once per
  `advance-phase` call. `current_phase`, `active_player`, and `battle_round` are all
  derived from it (`app/phases.py`) rather than stored — they can't drift out of sync.
- **`ActiveEffect.expired`**: computed at read time from `duration_type` +
  `created_at_step`, never auto-deleted. Matches the app's "surface consequences, don't
  enforce them" philosophy — dismissal is still the explicit `DELETE .../effects/{id}`.
- **`docs/app-plan.md`**, which `docs/webapp-skeleton-spec.md` says to read for full
  context, isn't actually present in this repo — only `webapp-skeleton-spec.md` and
  `SESSION-SUMMARY.md` exist under `docs/`. Built from those two directly; flag if
  `app-plan.md` should be added back.
