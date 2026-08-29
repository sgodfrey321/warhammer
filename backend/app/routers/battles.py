from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import phases
from ..db import get_session
from ..models import ActiveEffect, BattleSession, PlayerState, Unit, UnitSynergy, UnitTurnState

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
    flags: Optional[list[str]] = None


class ActiveEffectOut(BaseModel):
    id: int
    label: str
    owner_player: int
    duration_type: str
    created_at_step: int
    lifts_restriction: Optional[str]
    expired: bool


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


def _get_battle_or_404(battle_id: int, session: Session) -> BattleSession:
    battle = session.get(BattleSession, battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    return battle


def _to_out(battle: BattleSession, session: Session) -> BattleOut:
    step = battle.global_step
    phase = phases.current_phase(step)

    players = session.exec(
        select(PlayerState).where(PlayerState.battle_session_id == battle.id)
    ).all()

    effects = session.exec(
        select(ActiveEffect).where(ActiveEffect.battle_session_id == battle.id)
    ).all()
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
        active_synergies = session.exec(
            select(UnitSynergy).where(
                UnitSynergy.roster_id == battle.roster_id,
                UnitSynergy.trigger_phase == phase,
            )
        ).all()

    return BattleOut(
        id=battle.id,
        started_at=battle.started_at.isoformat(),
        roster_id=battle.roster_id,
        global_step=step,
        battle_round=phases.battle_round(step),
        active_player=phases.active_player(step),
        current_phase=phase,
        players=players,
        effects=effects_out,
        active_synergies=active_synergies,
    )


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


@router.patch("/{battle_id}/advance-phase", response_model=BattleOut)
def advance_phase(battle_id: int, session: Session = Depends(get_session)):
    battle = _get_battle_or_404(battle_id, session)
    battle.global_step += 1
    session.add(battle)
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


@router.patch("/{battle_id}/units/{unit_id}/turn-state", response_model=UnitTurnState)
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
    return state
