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
| `tools/bsdata-indexer/` | Builds `UnitDefinition` reference JSON (stats, abilities, weapon profiles, points) from BSData's BattleScribe catalogues + the Munitorum Field Manual points snapshot. Optional second stage extracts synergy candidates from ability text. |
| `backend/` | FastAPI + SQLite API implementing the Roster Builder + Battle Tracker — rosters, units, leader/bodyguard attachments, synergies, resource pools, and the battle phase engine. |
| `frontend/` | React + Vite + TypeScript UI for the backend above. |
| `docs/` | The specs this was built from (`webapp-skeleton-spec.md`, `battle-engine-spec.md`), a running cleanup list (`TODO.md`), and session notes. |
| `dev.py` | Starts the backend and frontend dev servers together; tears down the whole process tree on Ctrl+C. |

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

## Tests

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest
cd tools/bsdata-indexer && ../../.venv/Scripts/python.exe -m pytest
cd frontend && npm run build
```
