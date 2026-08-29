# Battle round engine — detailed implementation spec

## Purpose
The skeleton PoC proved the basic loop (create roster → battle → advance through 5 phases → one effect resolves → one synergy surfaces). This spec details the actual per-phase behavior for all five phases, so the engine reflects everything validated against real rules and real mockups this session — not just the generic advance-a-phase mechanic.

Read `docs/app-plan.md` first, especially the "Battle Tracker — phase model" and "Cross-stage state: the scope ladder" sections. This spec operationalizes those into concrete logic.

## New schema addition: `DeclaredStatePool`
Not previously formalized. Needed for Battle Focus tokens (Aeldari, round-scoped, spendable, non-stacking pool) and Blessings of Khorne (World Eaters, phase-scoped, stacking, dice-driven). Add to `app-plan.md`'s data model:

```
DeclaredStatePool   (definition — could live on Roster or be faction/detachment metadata)
- id, roster_id, name, max_value, scope ("battle_round" | "phase" | "turn"), stacking (bool)

DeclaredStatePoolState   (runtime — lives on the BattleSession, one per pool per owning player)
- id, battle_session_id, pool_id, owner_player, current_value
```

`stacking: false` pools (Battle Focus) refill to `max_value` at the start of their scope and get consumed by spending. `stacking: true` pools (Blessings of Khorne) don't "refill" so much as accumulate new entries each time their scope restarts — model this as a list of active blessing instances rather than a single number, if the two turn out to need meaningfully different runtime shapes.

## Battle round / turn transition logic

```
PHASES = [command, movement, shooting, charge, fight]

def advance_phase(session):
    if session.current_phase != "fight":
        next_phase = PHASES[PHASES.index(session.current_phase) + 1]
        transition_type = "phase_end"
    elif session.active_player == 1:
        next_phase = "command"
        session.active_player = 2
        transition_type = "turn_end"
    else:  # fight phase, player 2 — battle round rolls over
        next_phase = "command"
        session.active_player = 1
        session.battle_round += 1
        transition_type = "battle_round_end"

    check_active_effects(session, transition_type)          # see below
    if next_phase == "command":
        grant_core_cp(session)                                # both players, every Command phase
    if transition_type == "battle_round_end":
        refill_round_scoped_pools(session)                    # Battle Focus etc.
    reset_phase_acknowledged_synergies(session)               # synergy reminders reappear each entry
    session.current_phase = next_phase
```

## Active Effect boundary-checking (generalizes across all phases)

Run on every transition, checking every `ActiveEffect` on the session:

| `duration_type` | Flag for dismissal when... |
|---|---|
| `end_of_phase` | the phase that just ended matches the phase the effect was created in |
| `end_of_turn` | the turn that just ended belongs to the effect's `owner_player` |
| `end_of_battle_round` | a battle-round boundary was just crossed |
| `until_next_command_phase` | entering Command phase **and** `session.active_player == effect.owner_player` (player-relative — this is the Farseer case; it must NOT fire on the opponent's Command phase) |
| `until_condition_clears`, `manual` | never auto-flagged — dismissed only by explicit user action |

Flagging means marking the effect for review, not deleting it — the person confirms dismissal (matches the mockups' "Dismiss" button pattern throughout).

## Unit Synergy surfacing

On entering a phase: query the attached roster's `UnitSynergy` records where `trigger_phase` matches the phase just entered. Show each as a reminder unless already acknowledged *this specific phase instance*. Acknowledgment resets every time the phase is re-entered (next turn, next round) — a synergy reminder should reappear every time it's relevant, not just once ever.

## Per-phase behavior

### Command phase
- **Start**: run the generic Active Effect check (above). If this is the first Command phase of a new battle round (i.e. `active_player == 1` and it's the start of the round), also refill round-scoped `DeclaredStatePool`s.
- **Gain Core CP**: both players' `cp_gained += 1`, automatically, every time Command phase is entered — not once per round, once per Command phase instance (which happens once per player turn, so twice per round).
- **Battle-shock**: surface as a manual checklist reminder for the active player only. The app doesn't track individual unit wounds, so this can't be automated — it's a prompt, not a computed check.
- **Command abilities**: this is a free-input window — player may spend CP (stratagems), use faction/detachment abilities (this is where Vessels of Wrath's Archslaughterer-style once-per-battle activations would fire), and log any resulting `ActiveEffect`.
- **End**: standard end-of-phase Active Effect check.

### Movement phase
- Present the unit selection list in stable roster order (per the earlier UX decision — no relevance-sorting).
- Selecting a unit and assigning a `move_type` (stationary/normal/advance/fall_back/disembark/ingress) writes a `UnitTurnState` row for `(unit, battle_round, turn_owner)`.
- If `move_type` is `advance` or `fall_back`, surface a **non-blocking warning** when that unit is later selected in Shooting/Charge: "this unit normally can't [shoot/charge] this turn." Don't hard-block — the person may have a mitigation the app doesn't know about (Star Engines, Assault weapons, etc.), per the plan's "eligibility is resolved, not hardcoded" principle.
- If the roster has a movement-related `DeclaredStatePool` spend available (Swift as the Wind-style), surface it as an optional action on the selected unit, tied to the pool's current value.
- **End**: standard check.

### Shooting phase
- Surface any `UnitSynergy` reminders matching this phase (the Farseer/Dire Avengers case) before/alongside unit selection.
- Selecting a unit sets `has_shot = true` on its `UnitTurnState`. If that unit's `move_type` was `advance`/`fall_back`, show the warning described above rather than blocking selection.
- **End**: standard check — this is also where the Farseer-style "mark a target" effect would be created if the ability's trigger is end-of-phase rather than start (verify against the specific ability's actual trigger wording, don't assume).

### Charge phase
- Declaring a charge may involve a **declared choice at declaration time** (Scent of Blood-style conditional bonus) — present as a choice at that moment, not a phase-level setting.
- **End of phase** is a real trigger point for faction-specific abilities (Khârn's end-of-Charge-phase check was the concrete example this session) — these need a way to be attached to a roster/unit. For now, this likely means **manual entry** of end-of-phase reminders per unit (the synergy-enrichment pipeline's Tier 1/2 extraction could eventually populate these automatically, but that's not yet wired up to end-of-phase triggers specifically — check `tools/synergy-enrichment/SPEC.md` before assuming it covers this case, it was scoped around synergies between units, not solo end-of-phase triggers).

### Fight phase — partially unresolved, build the outer shell only
This phase has an internal sequencing problem (Fights First units alternate-select before everyone else, then pile-in → fight → consolidate) that **was never fully designed this session** — flagged repeatedly as an open thread and still open. For this pass:
- Implement the outer sub-steps (start / pile-in / fight / consolidate / end) as checklist items, same shape as the other phases.
- Track which units have `has_fought = true`, and let the player mark a unit as having Fights First (informational tag), but **don't attempt to enforce or automate the alternating activation order** — that needs its own design pass first. Building an incorrect automated sequence would be worse than leaving it manual.
- Stacking declared state (Blessings of Khorne-style): each new roll appends to the active list for the phase rather than replacing what's there; clear the whole list at end of phase (matches its `end_of_phase` duration shown in the mockup).
- Per-enemy-unit-once-per-phase reactive triggers (Terror of Khorne-style): track usage as `(ability, enemy_unit_identifier, phase_instance)` if you want to enforce the "once per enemy unit" limit — but per the plan's own note when this was designed, enforcing this is optional; surfacing the reminder without enforcement is an acceptable v1.

## What to explicitly not build yet
- Full Fights First automation (see above — needs its own spec).
- Automatic extraction of end-of-phase unit-specific triggers (Khârn-style) — manual entry for now.
- Anything from the app-plan's other deferred sections (Mission/VP structure, Battlefield Photo, opponent-roster visibility) — unrelated to this spec, don't let phase-engine work creep into them.
