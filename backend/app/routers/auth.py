from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import bearer_token, get_current_user, hash_password, new_token, verify_password
from ..db import get_session
from ..models import AuthSession, User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


def _issue_token(user: User, session: Session) -> AuthOut:
    token = new_token()
    session.add(AuthSession(token=token, user_id=user.id))
    session.commit()
    return AuthOut(token=token, user=UserOut(id=user.id, username=user.username))


@router.post("/register", response_model=AuthOut)
def register(payload: Credentials, session: Session = Depends(get_session)):
    """Create an account and log it in (returns a token). Usernames are unique after trimming."""
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=422, detail="Username and password are required")
    if session.exec(select(User).where(User.username == username)).first() is not None:
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(username=username, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return _issue_token(user, session)


@router.post("/login", response_model=AuthOut)
def login(payload: Credentials, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == payload.username.strip())).first()
    # Verify even when the user is missing (against a throwaway hash) so a wrong username and a
    # wrong password take about the same time -- doesn't leak which usernames exist.
    reference = user.password_hash if user else hash_password("_")
    if not verify_password(payload.password, reference) or user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return _issue_token(user, session)


@router.post("/logout", status_code=204)
def logout(token: str = Depends(bearer_token), session: Session = Depends(get_session)):
    auth = session.get(AuthSession, token)
    if auth is not None:
        session.delete(auth)
        session.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username)
