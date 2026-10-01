# Warhammer Manager

A Warhammer 40k army-management app: Roster Builder + Battle Tracker, backed by real
unit data pulled from the community BattleScribe project rather than hand-entered.
Currently a PoC — the plumbing is proven end-to-end, the UI is deliberately plain.

**License note**: unit stats, points, and rules text are Games Workshop's copyrighted
content, mirrored by the community-maintained [BSData](https://github.com/BSData)
project. See `tools/bsdata-indexer/README.md`'s license caveat before this is used
beyond your own private reference.

## Layout

| Path | What it is |
|---|---|
| `tools/bsdata-indexer/` | Builds `UnitDefinition` reference JSON (stats, abilities, weapon profiles, per-model-type profiles, points) from BSData's BattleScribe catalogues + the Munitorum Field Manual points snapshot. Optional second stage extracts synergy candidates from ability text. |
| `tools/gdmissions/` | Fetches 11th-edition Primary Mission, Secondary Mission, and deployment Layout data from the fan site gdmissions.app — powers the `/missions` page and the Battle Setup flow. |
| `backend/` | FastAPI + SQLite API implementing the Roster Builder + Battle Tracker — rosters, units, leader/bodyguard attachments, synergies, resource pools, mission/disposition battle setup, and the battle phase engine. |
| `frontend/` | React + Vite + TypeScript UI for the backend above. |
| `docs/` | The specs this was built from (`webapp-skeleton-spec.md`, `battle-engine-spec.md`), a running cleanup list (`TODO.md`), and session notes. |
| `dev.py` | Starts the backend and frontend dev servers together; tears down the whole process tree on Ctrl+C. |
| `docker-compose.yml` | Runs the whole app in containers — no local Python/Node setup needed. See "Run with Docker" below. |

## Quickstart

```bash
# one-time setup
.venv/Scripts/python.exe -m pip install -e "backend[dev]"
cd frontend && npm install && cd ..

# populate real unit data (run once, or after a dataslate update)
cd backend && ../.venv/Scripts/python.exe -m scripts.import_unit_definitions && cd ..

# run everything
python dev.py
```

Then open `http://localhost:5173`. See `backend/README.md` and `frontend/README.md`
for what each side actually does; `tools/bsdata-indexer/README.md` for how the unit
data is built and its known gaps; `docs/TODO.md` for open cleanup items.

## Run with Docker

No local Python/Node setup at all — just Docker:

```bash
docker compose up --build
```

This builds the backend (FastAPI, auto-importing the unit reference data on every startup —
safe to re-run, see `backend/README.md`) and the frontend (built once and served by nginx),
then opens the same `http://localhost:5173` as above. The database lives in a named Docker
volume (`warhammer-data`), so it survives `docker compose down`/`up` and image rebuilds.

Also reachable from other machines on your home LAN at `http://<this-machine's-192.168.x.x>:5173`
(see `backend/README.md` if a machine can't connect — likely Windows Firewall).

A code change needs a rebuild to take effect (`docker compose up --build`) — this mode trades
hot reload for a lighter, no-Node-at-runtime image; use `python dev.py` instead for active
development.

## Tests

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest
cd tools/bsdata-indexer && ../../.venv/Scripts/python.exe -m pytest
cd tools/gdmissions && ../../.venv/Scripts/python.exe -m pytest
cd frontend && npm run build
```
