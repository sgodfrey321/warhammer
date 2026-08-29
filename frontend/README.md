# Frontend (PoC)

React + Vite + TypeScript UI for `docs/webapp-skeleton-spec.md`, calling the FastAPI
backend in `../backend`. Utilitarian PoC UI, not a polished build — proves the same 5
scenarios the backend's test suite proves, but clicked through.

## Run it

Needs the backend running first (see `../backend/README.md` — includes running the
importer so there's real unit data to search):

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Then, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` (or `5174` if `5173` is already taken — if so, add
that port to `allow_origins` in `backend/app/main.py`, since the backend's CORS
allowlist is explicit about which dev ports it trusts).

## Pages

- `/` — Roster list + create.
- `/rosters/:id` — Roster editor: search/add real `UnitDefinition`s (autocomplete
  against `GET /unit-definitions`), add Unit Synergies between roster units, "Start
  Battle".
- `/battles/:id` — Battle Tracker: Advance Phase button (drives the backend's
  `global_step` state machine), per-player CP/VP, Active Effects (log one, see its
  computed `expired` flag flip at the right phase/turn/round boundary), and a synergy
  banner that appears only during its `trigger_phase`.

## Verified

`npm run build` (TS + Vite) compiles clean. All 5 PoC scenarios were driven in a real
Chrome tab against a live backend with real imported Aeldari data (Farseer + Dire
Avengers, an `until_next_command_phase` "Doom" effect surviving the opponent's whole
turn and expiring exactly on the owner's next Command phase, and the synergy banner
appearing only during the Shooting phase) — not just confirmed to build.

## Known rough edges (PoC, not polished)

- No loading/error states beyond a bare error string.
- No delete-roster or edit-detachments UI (endpoints exist, just not wired up here).
- No `UnitTurnState` UI (per-unit move/shot/charge/fight tracking) — the endpoint
  exists in the backend but this pass focused on the 5 spec scenarios, which don't
  require it.
