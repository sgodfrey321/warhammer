from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client(session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as c:
        # Rosters/battles are owner-scoped, so most tests need to be authenticated. Register a
        # default user and set its bearer token for the life of the client. Tests exercising
        # auth itself (unauthenticated calls, a second user) can override or clear this header.
        token = c.post("/auth/register", json={"username": "tester", "password": "pw"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(client):
    """Register another user and return an (id, token) for cross-owner isolation tests."""

    def _make(username: str, password: str = "pw") -> tuple[int, str]:
        body = client.post("/auth/register", json={"username": username, "password": password}).json()
        return body["user"]["id"], body["token"]

    return _make
