from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import phases
from ..db import get_session
from ..models import (
    ActiveEffect,
    BattleSession,
    DeclaredStatePool,
    DeclaredStatePoolEntry,
    DeclaredStatePoolState,
    PlayerState,
    SynergyAcknowledgment,
    Unit,
    UnitSynergy,
    UnitTurnState,
)

router = APIRouter(prefix="/battles", tags=["battles"])


class BattleCreate(BaseModel):
    roster_id: Optional[int] = None


class PlayerStateUpdate(BaseModel):
    cp_gained: Optional[int] = None
    cp_spent: Optional[int] = None
    vp: Optional[int] = None


class EffectCreate(BaseModel):
    label: str
    owner_player: int
    duration_type: str
    lifts_restriction: Optional[str] = None


class TurnStateUpdate(BaseModel):
    move_type: Optional[str] = None
    has_shot: Optional[bool] = None
    has_charged: Optional[bool] = None
    has_fought: Optional[bool] = None
    is_fights_first: Optional[bool] = None
    flags: Optional[list[str]] = None


class PoolSpend(BaseModel):
    amount: int = 1


class PoolAdd(BaseModel):
    owner_player: int
    value: int


class ActiveEffectOut(BaseModel):
    id: int
    label: str
    owner_player: int
    duration_type: str
    created_at_step: int
    lifts_restriction: Optional[str]
    expired: bool


class TurnStateOut(BaseModel):
    id: int
    unit_id: int
    battle_round: int
    turn_owner: int
    move_type: Optional[str]
    has_shot: bool
    has_charged: bool
    has_fought: bool
    is_fights_first: bool
    flags: list[str]
    eligibility_warning: Optional[str]


class PoolStateOut(BaseModel):
    pool_id: int
    name: str
    max_value: int
    scope: str
    owner_player: int
    current_value: int


class PoolEntryOut(BaseModel):
    id: int
    pool_id: int
    name: str
    scope: str
    owner_player: int
    value: int
    created_at_step: int


class BattleOut(BaseModel):
    id: int
    started_at: str
    roster_id: Optional[int]
    global_step: int
    battle_round: int
    active_player: int
    current_phase: str
    players: list[PlayerState]
    effects: list[ActiveEffectOut]
    active_synergies: list[UnitSynergy]
    turn_states: list[TurnStateOut]
    pool_states: list[PoolStateOut]
    pool_entries: list[PoolEntryOut]


def _get_battle_or_404(battle_id: int, session: Session) -> BattleSession:
    battle = session.get(BattleSession, battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    return battle


def _to_turn_state_out(state: UnitTurnState) -> TurnStateOut:
    return TurnStateOut(
        id=state.id,
        unit_id=state.unit_id,
        battle_round=state.battle_round,
        turn_owner=state.turn_owner,
        move_type=state.move_type,
        has_shot=state.has_shot,
        has_charged=state.has_charged,
        has_fought=state.has_fought,
        is_fights_first=state.is_fights_first,
        flags=state.flags,
        eligibility_warning=phases.eligibility_warning(
            move_type=state.move_type, has_shot=state.has_shot, has_charged=state.has_charged
        ),
    )


def _to_out(battle: BattleSession, session: Session) -> BattleOut:
    step = battle.global_step
    phase = phases.current_phase(step)
    round_ = phases.battle_round(step)

    players = session.exec(select(PlayerState).where(PlayerState.battle_session_id == battle.id)).all()

    effects = session.exec(select(ActiveEffect).where(ActiveEffect.battle_session_id == battle.id)).all()
    effects_out = [
        ActiveEffectOut(
            id=e.id,
            label=e.label,
            owner_player=e.owner_player,
            duration_type=e.duration_type,
            created_at_step=e.created_at_step,
            lifts_restriction=e.lifts_restriction,
            expired=phases.is_expired(
                duration_type=e.duration_type,
                owner_player=e.owner_player,
                created_at_step=e.created_at_step,
                current_step=step,
            ),
        )
        for e in effects
    ]

    active_synergies: list[UnitSynergy] = []
    if battle.roster_id is not None:
        acknowledged_ids = {
            a.synergy_id
            for a in session.exec(
                select(SynergyAcknowledgment).where(
                    SynergyAcknowledgment.battle_session_id == battle.id,
                    SynergyAcknowledgment.step == step,
                )
            ).all()
        }
        active_synergies = [
            s
            for s in session.exec(
                select(UnitSynergy).where(
                    UnitSynergy.roster_id == battle.roster_id,
                    UnitSynergy.trigger_phase == phase,
                )
            ).all()
            if s.id not in acknowledged_ids
        ]

    turn_states = session.exec(
        select(UnitTurnState).where(
            UnitTurnState.battle_session_id == battle.id,
            UnitTurnState.battle_round == round_,
        )
    ).all()

    pools: list[DeclaredStatePool] = []
    if battle.roster_id is not None:
        pools = session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == battle.roster_id)).all()
    pools_by_id = {p.id: p for p in pools}

    pool_states_out: list[PoolStateOut] = []
    pool_entries_out: list[PoolEntryOut] = []
    if pools:
        pool_ids = list(pools_by_id)
        for state in session.exec(
            select(DeclaredStatePoolState).where(
                DeclaredStatePoolState.battle_session_id == battle.id,
                DeclaredStatePoolState.pool_id.in_(pool_ids),
            )
        ).all():
            pool = pools_by_id[state.pool_id]
            pool_states_out.append(
                PoolStateOut(
                    pool_id=pool.id,
                    name=pool.name,
                    max_value=pool.max_value,
                    scope=pool.scope,
                    owner_player=state.owner_player,
                    current_value=state.current_value,
                )
            )
        for entry in session.exec(
            select(DeclaredStatePoolEntry).where(
                DeclaredStatePoolEntry.battle_session_id == battle.id,
                DeclaredStatePoolEntry.pool_id.in_(pool_ids),
            )
        ).all():
            pool = pools_by_id[entry.pool_id]
            pool_entries_out.append(
                PoolEntryOut(
                    id=entry.id,
                    pool_id=pool.id,
                    name=pool.name,
                    scope=pool.scope,
                    owner_player=entry.owner_player,
                    value=entry.value,
                    created_at_step=entry.created_at_step,
                )
            )

    return BattleOut(
        id=battle.id,
        started_at=battle.started_at.isoformat(),
        roster_id=battle.roster_id,
        global_step=step,
        battle_round=round_,
        active_player=phases.active_player(step),
        current_phase=phase,
        players=players,
        effects=effects_out,
        active_synergies=active_synergies,
        turn_states=[_to_turn_state_out(s) for s in turn_states],
        pool_states=pool_states_out,
        pool_entries=pool_entries_out,
    )


@router.get("", response_model=list[BattleOut])
def list_battles(roster_id: Optional[int] = None, session: Session = Depends(get_session)):
    """The database has always persisted every battle (SQLite, durable across restarts) --
    what was missing was any way to find one again without already knowing its id. Filter
    by roster_id for "which battles has this roster played" (a roster can have more than
    one, e.g. replaying the same list); omit it to list every battle."""
    query = select(BattleSession)
    if roster_id is not None:
        query = query.where(BattleSession.roster_id == roster_id)
    battles = session.exec(query.order_by(BattleSession.started_at.desc())).all()
    return [_to_out(b, session) for b in battles]


@router.post("", response_model=BattleOut)
def create_battle(payload: BattleCreate, session: Session = Depends(get_session)):
    battle = BattleSession(roster_id=payload.roster_id)
    session.add(battle)
    session.commit()
    session.refresh(battle)

    for player_number in (1, 2):
        session.add(PlayerState(battle_session_id=battle.id, player_number=player_number))
    session.commit()

    return _to_out(battle, session)


@router.get("/{battle_id}", response_model=BattleOut)
def get_battle(battle_id: int, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    return _to_out(battle, session)


def _get_or_create_pool_state(
    session: Session, battle_id: int, pool: DeclaredStatePool, owner_player: int
) -> DeclaredStatePoolState:
    """A pool starts full the first time it's referenced in a battle -- a Battle Focus
    pool is available from turn 1, not empty until the first round boundary refills it."""
    state = session.exec(
        select(DeclaredStatePoolState).where(
            DeclaredStatePoolState.battle_session_id == battle_id,
            DeclaredStatePoolState.pool_id == pool.id,
            DeclaredStatePoolState.owner_player == owner_player,
        )
    ).first()
    if state is None:
        state = DeclaredStatePoolState(
            battle_session_id=battle_id, pool_id=pool.id, owner_player=owner_player, current_value=pool.max_value
        )
    return state


@router.patch("/{battle_id}/advance-phase", response_model=BattleOut)
def advance_phase(battle_id: int, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    old_step = battle.global_step
    transition = phases.transition_type(old_step)
    battle.global_step = old_step + 1
    session.add(battle)

    if phases.current_phase(battle.global_step) == "command":
        # Both players gain Core CP every Command phase instance (once per player turn,
        # so twice per round) -- not a once-per-round grant.
        for player in session.exec(select(PlayerState).where(PlayerState.battle_session_id == battle_id)).all():
            player.cp_gained += 1
            session.add(player)

    if battle.roster_id is not None:
        ending = phases.scopes_ending(transition)
        pools = session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == battle.roster_id)).all()
        for pool in pools:
            if pool.scope not in ending:
                continue
            if pool.stacking:
                entries = session.exec(
                    select(DeclaredStatePoolEntry).where(
                        DeclaredStatePoolEntry.battle_session_id == battle_id,
                        DeclaredStatePoolEntry.pool_id == pool.id,
                    )
                ).all()
                for entry in entries:
                    session.delete(entry)
            else:
                for owner in (1, 2):
                    state = _get_or_create_pool_state(session, battle_id, pool, owner)
                    state.current_value = pool.max_value
                    session.add(state)

    session.commit()
    session.refresh(battle)
    return _to_out(battle, session)


@router.patch("/{battle_id}/retreat-phase", response_model=BattleOut)
def retreat_phase(battle_id: int, session: Session = Depends(get_session)):
    """Steps global_step back by one, for correcting a misclick -- not a true undo.

    CP grants and DeclaredStatePool refill/clear that happened crossing that boundary
    forward are NOT reversed (stacking pool entries cleared going forward are gone for
    good; CP already granted stays granted). Both are already freely human-editable
    (CP via the player fields, pools via spend/add) if a retreat leaves them looking
    wrong -- matches the app's "bookkeeping, not a rules engine" philosophy.
    """
    battle = _get_battle_or_404(battle_id, session)
    if battle.global_step == 0:
        raise HTTPException(status_code=422, detail="Already at the start of the battle")
    battle.global_step -= 1
    session.add(battle)
    session.commit()
    session.refresh(battle)
    return _to_out(battle, session)

    session.commit()
    session.refresh(battle)
    return _to_out(battle, session)


@router.patch("/{battle_id}/players/{player_number}", response_model=PlayerState)
def update_player_state(
    battle_id: int, player_number: int, payload: PlayerStateUpdate, session: Session = Depends(get_session)
):
    _get_battle_or_404(battle_id, session)
    player = session.exec(
        select(PlayerState).where(
            PlayerState.battle_session_id == battle_id,
            PlayerState.player_number == player_number,
        )
    ).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found on this battle")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(player, field, value)
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


@router.post("/{battle_id}/effects", response_model=BattleOut)
def add_effect(battle_id: int, payload: EffectCreate, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    if payload.duration_type not in phases.DURATION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown duration_type: {payload.duration_type}")
    effect = ActiveEffect(
        battle_session_id=battle_id,
        created_at_step=battle.global_step,
        **payload.model_dump(),
    )
    session.add(effect)
    session.commit()
    return _to_out(battle, session)


@router.delete("/{battle_id}/effects/{effect_id}", response_model=BattleOut)
def dismiss_effect(battle_id: int, effect_id: int, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    effect = session.get(ActiveEffect, effect_id)
    if effect is None or effect.battle_session_id != battle_id:
        raise HTTPException(status_code=404, detail="Effect not found on this battle")
    session.delete(effect)
    session.commit()
    return _to_out(battle, session)


@router.post("/{battle_id}/synergies/{synergy_id}/acknowledge", response_model=BattleOut)
def acknowledge_synergy(battle_id: int, synergy_id: int, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    synergy = session.get(UnitSynergy, synergy_id)
    if synergy is None:
        raise HTTPException(status_code=404, detail="Synergy not found")
    ack = session.exec(
        select(SynergyAcknowledgment).where(
            SynergyAcknowledgment.battle_session_id == battle_id,
            SynergyAcknowledgment.synergy_id == synergy_id,
        )
    ).first()
    if ack is None:
        ack = SynergyAcknowledgment(battle_session_id=battle_id, synergy_id=synergy_id, step=battle.global_step)
    else:
        ack.step = battle.global_step
    session.add(ack)
    session.commit()
    return _to_out(battle, session)


@router.post("/{battle_id}/pools/{pool_id}/spend", response_model=BattleOut)
def spend_pool(battle_id: int, pool_id: int, payload: PoolSpend, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    pool = session.get(DeclaredStatePool, pool_id)
    if pool is None or pool.roster_id != battle.roster_id:
        raise HTTPException(status_code=404, detail="Pool not found on this battle's roster")
    if pool.stacking:
        raise HTTPException(status_code=422, detail="Stacking pools use /add, not /spend")

    spender = phases.active_player(battle.global_step)
    state = _get_or_create_pool_state(session, battle_id, pool, spender)
    state.current_value = max(0, state.current_value - payload.amount)
    session.add(state)
    session.commit()
    return _to_out(battle, session)


@router.post("/{battle_id}/pools/{pool_id}/add", response_model=BattleOut)
def add_pool_entry(battle_id: int, pool_id: int, payload: PoolAdd, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    pool = session.get(DeclaredStatePool, pool_id)
    if pool is None or pool.roster_id != battle.roster_id:
        raise HTTPException(status_code=404, detail="Pool not found on this battle's roster")
    if not pool.stacking:
        raise HTTPException(status_code=422, detail="Non-stacking pools use /spend, not /add")

    entry = DeclaredStatePoolEntry(
        battle_session_id=battle_id,
        pool_id=pool_id,
        owner_player=payload.owner_player,
        value=payload.value,
        created_at_step=battle.global_step,
    )
    session.add(entry)
    session.commit()
    return _to_out(battle, session)


@router.patch("/{battle_id}/units/{unit_id}/turn-state", response_model=TurnStateOut)
def update_turn_state(
    battle_id: int, unit_id: int, payload: TurnStateUpdate, session: Session = Depends(get_session)
):
    battle = _get_battle_or_404(battle_id, session)
    unit = session.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unit not found")

    round_ = phases.battle_round(battle.global_step)
    state = session.exec(
        select(UnitTurnState).where(
            UnitTurnState.battle_session_id == battle_id,
            UnitTurnState.unit_id == unit_id,
            UnitTurnState.battle_round == round_,
        )
    ).first()
    if state is None:
        state = UnitTurnState(
            battle_session_id=battle_id,
            unit_id=unit_id,
            battle_round=round_,
            turn_owner=phases.active_player(battle.global_step),
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(state, field, value)

    session.add(state)
    session.commit()
    session.refresh(state)
    return _to_turn_state_out(state)
