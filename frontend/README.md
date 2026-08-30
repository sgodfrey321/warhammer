# Frontend (PoC)

React + Vite + TypeScript UI for `docs/webapp-skeleton-spec.md` and
`docs/battle-engine-spec.md`, calling the FastAPI backend in `../backend`. Utilitarian
PoC UI, not a polished build — proves the plumbing works, not a design pass. One real
dependency beyond React/Vite/react-router: `recharts`, for the Roster Editor's Army
Analysis bar charts.

## Run it

Needs the backend running first (see `../backend/README.md` — includes running the
importer so there's real unit data to search):

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 0.0.0.0
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
allowlist is explicit about which dev ports it trusts). `vite.config.ts` sets
`server.host = true`, so it also binds every network interface — other machines on your
home LAN can open `http://<this-machine's-192.168.x.x>:5173` directly; `api.ts` resolves
the backend from the page's own hostname, so this works with no further config.

## Pages

- **`/` — Rosters**: list + create, plus a file picker to import a BattleScribe/
  NewRecruit roster export JSON directly (creates the roster, its units, their
  leader/bodyguard attachments, and their actual equipped loadouts, all in one step —
  reports how many units matched, didn't match, and how many attachments were found).
- **`/rosters/:id` — Roster Editor**: rename/delete the roster (delete cascades through
  every unit, attachment, synergy, pool, and battle it owns — see `backend/README.md`).
  Everything below lives in its own collapsible accordion (Units open by default):
  - **Units** — search/add real `UnitDefinition` data, grouped under Battlefield Role
    headers (Epic Hero, Character, Battleline, Vehicle, Infantry, ...; picked from each
    unit's keywords by a fixed priority order, since the indexed data has no single
    "primary category" field) with a points subtotal per group. A Character leading a
    bodyguard unit nests visually into that unit's own card instead of showing as a
    separate entry — its points still count toward its own role's subtotal, not the
    unit it's nested under (matches how the NewRecruit reference this was modeled on
    behaves). Click a unit's "details" link to open the **Unit Details modal**
    (`components/UnitDetailsModal.tsx`) — per-model-type stat rows, full Ranged/Melee
    weapon tables (only what's actually equipped, with real counts), and every combined
    unit's (leaders + the unit they lead) abilities merged and labeled.
  - **Army Analysis** — four bar charts computed client-side from the roster's units
    (`src/weapons.ts`, `src/units.ts`): Ranged Firepower and Melee Onslaught (total
    attacks by weapon Strength, dice-notation Attacks like D6 averaged), Movement (unit
    count by Movement value), and Save/Invulnerable Save (grouped bars on the same
    2+-to-7+ scale). Only counts units with a confirmed loadout (import-only) — a
    manually-added unit is called out as skipped rather than guessed at.
  - Unit Buffs, Unit Attachments, Unit Synergies, Declared State Pools — as before.
  - "Start Battle" now opens **Battle Setup** (see below) instead of creating a battle
    directly; a "Previous battles" list still links back to any battle already played.
- **`/battles/setup` — Battle Setup**: reached via "Start Battle" (`?rosterId=`, creates
  a new battle) or "Edit setup"/"Set up now" from the Battle Tracker (`?battleId=`,
  edits an existing one — setup is never one-shot). Opponent name (free text, autofilled
  from your existing rosters' names via a `<datalist>`), both players' Force Disposition,
  a layout picker (one image at a time, cycled, from `tools/gdmissions`' data), and a
  live preview of both sides' resulting Primary Mission — reads asymmetrically (your
  disposition row × their column), so you and your opponent can end up with different
  missions in the same game. Everything here is optional; "Start without a mission"
  skips straight to a bare battle.
- **`/battles/:id` — Battle Tracker**: a two-column layout — a sticky left column
  stays in view while the right column's Unit Turn States list scrolls independently.
  The left column: a slim mission-setup bar (dispositions + "Edit setup"/"Set up now"),
  the phase banner (Previous/Advance controls naming their destination phase), a synergy
  banner, and — stacked one above the other, Opponent then You — each player's CP
  controls plus their resolved Primary Mission's scoring tiers, each with a +/− counter
  (`achieved_count`) that drives their computed VP total server-side (a small "VP
  adjustment" field covers anything outside primary-mission scoring, e.g. secondary
  missions later). Declared State Pools (clickable token tally) and the Active Effects
  log follow. Advance/Previous Phase drive the backend's `global_step` state machine
  (phase/turn/round all update together, Core CP auto-grants both players every Command
  phase — going backward only moves the phase pointer, it doesn't undo CP grants or pool
  refill/clear). Each unit shows its stat line (with any declared buff badge inline),
  rule tags, and expandable abilities and weapons (full profile when the loadout item
  resolves against the catalogue, a bare name + "profile not indexed" when it doesn't —
  never hidden), plus any effects logged against that specific unit. Attached units (a
  Character leading a bodyguard squad) render as one grouped block sharing one set of
  controls, since they move/shoot/charge/fight as a combined unit. Active Effects show a
  computed `expired` flag (struck through) rather than disappearing on their own.
- **`/army-rules` — Army Rules**: every catalogue/library-level army rule pulled
  straight from BSData, grouped by faction and collapsed by default — reference text
  only, not tied to any roster or battle state yet.
- **`/missions` — Missions**: pick both players' Force Disposition to see the resulting
  Primary Mission on each side, a recommended deployment layout (with a "browse all
  layouts" option for every matchup, not just the selected one), and every Secondary
  Mission card — all sourced from `tools/gdmissions`' fetched data. Standalone reference,
  independent of Battle Setup's use of the same underlying data.

## Verified

`npm run build` (TS + Vite) compiles clean. Every feature above has been driven live in
a real Chrome tab against a running backend with real imported data (Aeldari and World
Eaters), not just confirmed to build — including cross-turn effect expiry, synergy
banner appear/disappear timing, `DeclaredStatePool` refill/clear at the right
boundaries, grouped-unit turn-state sync, weapon-loadout resolution (including
multi-firing-mode weapons like `Axe of Khorne - strike`/`-sweep`, matched back to a
roster's plain-named loadout item), the Battle Setup → Battle Tracker mission-scoring
flow end to end, and the Unit Details modal against a real combined leader+led group
(Asurmen leading Dire Avengers, a rank-and-file model + an Exarch with different stats).

## Known rough edges (PoC, not polished)

- No loading/error states beyond a bare error string.
- No edit-detachments UI (the endpoint exists, just not wired up here).
- The Unit Details modal's per-model-type Models table only has data for units with both
  a confirmed loadout *and* a re-generated (post-`model_profiles`) indexer output — a
  manually-added unit shows no Models table at all (see `docs/TODO.md`).
- No manual loadout-editing UI for hand-built (non-imported) rosters — see
  `docs/TODO.md`.
- Turn-state actions aren't phase-gated (you can mark `has_shot` while
  in the Movement phase) — see `docs/TODO.md`.
- No visual "done for this phase" treatment on units — see `docs/TODO.md`.
