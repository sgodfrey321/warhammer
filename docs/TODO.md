# PoC cleanup TODO

Skeleton-code-first: items found while clicking through the running app that aren't
worth stopping to fix mid-build, but should get cleaned up before this goes past PoC.
Add to this list as more turn up; don't let it silently grow stale.

## Roster import

- **Declared State Pools are only auto-populated for one faction so far.** The indexer now
  extracts catalogue/library-level army rules (`bsdata_indexer.army_rules`, surfaced
  read-only on the frontend's "Army Rules" tab), and `POST /rosters/import` auto-creates a
  `DeclaredStatePool` from them via `backend/app/army_rule_handlers/` -- but only where the
  rule is actually pool-shaped. So far that's just Battle Focus (Army Faction Asuryani/
  Aeldari): a non-stacking, `battle_round`-scoped pool sized off the roster's `battle_size`.
  Scoped World Eaters (Blessings of Khorne), Thousand Sons (Cabal of Sorcerers), and Space
  Marines (Oath of Moment) too -- none of them are countable-resource pools (dice-roll-and-
  choose, or a per-Command-phase declared target), so they don't get a handler here; they'd
  be better served by a Command/round-phase checklist reminder pointing at the existing
  Active Effects log (`until_next_command_phase`/`end_of_battle_round` duration types already
  exist) than by forcing them into the pool model. Every other faction, and any manually
  built (non-imported) roster regardless of faction, still needs pools added by hand via the
  roster editor's "Declared State Pools" form -- add a new file under `army_rule_handlers/`
  plus one registry entry to extend coverage.

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

## Unit Details modal

- **No per-model-type breakdown for manually-added units.** `UnitDetailsModal` matches
  `unit_definition.model_profiles` against that specific `Unit.model_groups` (roster
  instance) by name to build its Models table — both only ever get populated by
  `POST /rosters/import` (`model_profiles` from the bsdata-indexer, `model_groups` from
  `battlescribe_import.py`'s `_model_groups()`). A unit added by hand via
  `POST /rosters/{id}/units` has `model_groups: []`, so the modal shows nothing there
  even if the catalogue has real per-model-type data for it. Same shape of gap as the
  loadout-editing one below — would need a small form to let you declare which model
  types (and how many of each) a hand-built unit actually has.

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
