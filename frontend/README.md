# Frontend (PoC)

React + Vite + TypeScript UI for `docs/webapp-skeleton-spec.md` and
`docs/battle-engine-spec.md`, calling the FastAPI backend in `../backend`. Utilitarian
PoC UI, not a polished build — proves the plumbing works, not a design pass.

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

Or use `../dev.py` from the repo root to start both together (and tear both down
cleanly on Ctrl+C).

Opens on `http://localhost:5173` (or `5174` if `5173` is already taken — if so, add
that port to `allow_origins` in `backend/app/main.py`, since the backend's CORS
allowlist is explicit about which dev ports it trusts).

## Pages

- **`/` — Rosters**: list + create, plus a file picker to import a BattleScribe/
  NewRecruit roster export JSON directly (creates the roster, its units, their
  leader/bodyguard attachments, and their actual equipped loadouts, all in one step —
  reports how many units matched, didn't match, and how many attachments were found).
- **`/rosters/:id` — Roster Editor**: unit search/add (real `UnitDefinition` data, with
  a compact loadout summary per unit when one exists), Unit Attachments (leader/led,
  auto-populated by import or added by hand), Unit Synergies, Declared State Pools
  (Battle Focus/Blessings-of-Khorne-style resource pools), "Start Battle", and a
  "Previous battles" list linking back to any battle already played with this roster.
- **`/battles/:id` — Battle Tracker**: Advance Phase button (drives the backend's
  `global_step` state machine — phase/turn/round all update together, Core CP
  auto-grants both players every Command phase), per-player CP/VP, Declared State Pool
  spend/add controls, a synergy banner (with an "acknowledge" action) that appears only
  during its `trigger_phase`, and Unit Turn States: move type / shot / charged / fought
  / fights-first per unit, each showing its stat line and expandable abilities and
  weapons (full profile when the loadout item resolves against the catalogue, a bare
  name + "profile not indexed" when it doesn't — never hidden). Attached units (a
  Character leading a bodyguard squad) render as one grouped block sharing one set of
  controls, since they move/shoot/charge/fight as a combined unit. Active Effects show
  a computed `expired` flag (struck through) rather than disappearing on their own.

## Verified

`npm run build` (TS + Vite) compiles clean. Every feature above has been driven live in
a real Chrome tab against a running backend with real imported data (Aeldari and World
Eaters), not just confirmed to build — including cross-turn effect expiry, synergy
banner appear/disappear timing, `DeclaredStatePool` refill/clear at the right
boundaries, grouped-unit turn-state sync, and weapon-loadout resolution (including
multi-firing-mode weapons like `Axe of Khorne - strike`/`-sweep`, matched back to a
roster's plain-named loadout item).

## Known rough edges (PoC, not polished)

- No loading/error states beyond a bare error string.
- No delete-roster or edit-detachments UI (endpoints exist, just not wired up here).
- No manual loadout-editing UI for hand-built (non-imported) rosters — see
  `docs/TODO.md`.
- Turn-state controls aren't gated to the current phase (you can mark `has_shot` while
  in the Movement phase) — see `docs/TODO.md`.
- No visual "done for this phase" treatment on units — see `docs/TODO.md`.
