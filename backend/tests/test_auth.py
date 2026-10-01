from __future__ import annotations


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_and_logout(client):
    # The client fixture already registered "tester"; register a fresh account here.
    reg = client.post("/auth/register", json={"username": "alice", "password": "hunter2"})
    assert reg.status_code == 200
    body = reg.json()
    token = body["token"]
    assert body["user"]["username"] == "alice"

    me = client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    # Re-login issues a working token too.
    login = client.post("/auth/login", json={"username": "alice", "password": "hunter2"})
    assert login.status_code == 200
    assert client.get("/auth/me", headers=_auth(login.json()["token"])).status_code == 200

    # Logout invalidates the token it was made with.
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 204
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_register_rejects_duplicate_username(client):
    assert client.post("/auth/register", json={"username": "bob", "password": "pw"}).status_code == 200
    dup = client.post("/auth/register", json={"username": "bob", "password": "other"})
    assert dup.status_code == 409


def test_login_wrong_password_is_401(client):
    client.post("/auth/register", json={"username": "carol", "password": "right"})
    assert client.post("/auth/login", json={"username": "carol", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_rosters_require_authentication(client):
    resp = client.get("/rosters", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    # No header at all is also rejected.
    del client.headers["Authorization"]
    assert client.get("/rosters").status_code == 401


def test_rosters_are_isolated_per_user(client, make_user):
    # tester (the default client user) owns this roster.
    roster = client.post("/rosters", json={"name": "Mine", "faction": "Aeldari - Craftworlds"}).json()

    _, other_token = make_user("intruder")
    other = _auth(other_token)

    # The other user sees none of tester's rosters, and can't fetch/patch/delete the one by id.
    assert client.get("/rosters", headers=other).json() == []
    assert client.get(f"/rosters/{roster['id']}", headers=other).status_code == 404
    assert client.patch(f"/rosters/{roster['id']}", json={"name": "Hax"}, headers=other).status_code == 404
    assert client.delete(f"/rosters/{roster['id']}", headers=other).status_code == 404
    # Nested resources are protected by the same ownership check.
    assert client.get(f"/rosters/{roster['id']}/units", headers=other).status_code == 404

    # tester still sees their own roster untouched.
    mine = client.get("/rosters").json()
    assert [r["id"] for r in mine] == [roster["id"]]
    assert mine[0]["name"] == "Mine"


def test_battles_are_isolated_per_user(client, make_user):
    battle = client.post("/battles", json={}).json()
    _, other_token = make_user("intruder2")
    other = _auth(other_token)

    assert client.get("/battles", headers=other).json() == []
    assert client.get(f"/battles/{battle['id']}", headers=other).status_code == 404
    # Owner still sees it.
    assert [b["id"] for b in client.get("/battles").json()] == [battle["id"]]
