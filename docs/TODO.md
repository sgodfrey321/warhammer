# PoC cleanup TODO

Skeleton-code-first: items found while clicking through the running app that aren't
worth stopping to fix mid-build, but should get cleaned up before this goes past PoC.
Add to this list as more turn up; don't let it silently grow stale.

## Roster import

- **Declared State Pools aren't auto-populated.** Nothing creates a roster's pools
  (Battle Focus, Blessings of Khorne, etc.) automatically -- not the indexer (it
  doesn't extract this data at all), not `POST /rosters/import` (BattleScribe import
  only creates `Unit` rows). Importing a real Aeldari list gets you units + points but
  no Battle Focus pool; it has to be added by hand via the roster editor's "Declared
  State Pools" form. Eventually this probably wants to be faction-level data (every
  Aeldari roster gets the same Battle Focus rules) rather than something each roster
  declares from scratch -- but that needs the indexer/enrichment side to actually
  produce it first; don't build the app-side auto-creation ahead of a real data source.

- **No manual loadout editing for hand-built rosters.** `Unit.loadout` (weapon
  name/count) is only ever populated by `POST /rosters/import` -- a roster built from
  scratch via `POST /rosters/{id}/units` gets `loadout: []` and stays that way. The
  Battle Tracker's weapons toggle no longer shows *nothing* for these units (it falls
  back to listing `unit_definition.weapons` as unconfirmed catalogue options, clearly
  labeled "No chosen loadout on this roster"), but there's still no way to actually
  *pick* a specific loadout for a manually-added unit the way import does automatically.
  Same shape of gap as attachments/synergies/pools already had before their manual-add
  forms were built -- needs the same treatment (a small form in `RosterEditor.tsx`
  letting you pick from `unit_definition.weapons` and a count).

## Battle Tracker

- **Turn-state actions aren't phase-gated.** `PATCH /battles/{id}/units/{unit_id}/turn-state`
  (`backend/app/routers/battles.py`) accepts any field regardless of `current_phase` --
  e.g. `move_type` can be set while in the Shooting phase, `has_shot` while in Movement.
  The frontend's Unit Turn States section (`frontend/src/pages/BattleTracker.tsx`) shows
  every control (move type, shot/charged/fought) at once instead of only the one
  relevant to the phase just entered. Needs both a backend validation (reject/ignore
  fields that don't belong to `current_phase`) and a frontend change (only render the
  phase-relevant control, or disable the others).

- **No visual "done for this phase" state.** Once a unit's phase-relevant action is
  taken (moved in Movement, shot in Shooting, charged in Charge, fought in Fight), the
  unit should gray out to show it's handled -- currently it just sits there identical
  to an untouched unit, so it's easy to lose track of who's left mid-phase.
  Sam suggested possibly moving acted units to the bottom of the list, too -- note this
  is in tension with the earlier session decision recorded in `docs/SESSION-SUMMARY.md`
  ("Unit lists don't reorder for relevance... Moved units stay in place, dimmed -- not
  moved to a separate 'done' list"). Revisit which one actually feels right at the
  table rather than assuming the old decision still holds now that it's clickable.

- **Attached-unit turn-state sync isn't atomic.** A Character leading a bodyguard unit
  (`UnitAttachment`, `backend/app/models.py`) shares one set of Movement/Shooting/
  Charge/Fight controls in the UI (`groupUnits()`/`handleTurnStateChange()` in
  `frontend/src/pages/BattleTracker.tsx`), but syncing them is multiple sequential
  `PATCH .../turn-state` calls from the frontend, not one backend transaction. A
  mid-sequence network failure could leave a group's units briefly out of sync until
  the next successful edit. Would need a backend group-update endpoint (resolve the
  full attachment group server-side, update every member's `UnitTurnState` in one
  transaction) to close this properly.
