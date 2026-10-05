import asyncio
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.accounts import SESSION_COOKIE
from app.core.config import Settings
from app.main import create_app
from app.services.account_store import InMemoryAccountStore, User
from test_main import FakeAnalyzer, FakeRecommender


HEADERS = {"X-MovieMatch-Request": "1", "Origin": "http://testserver"}
PASSWORD = "Une longue phrase secrète!"


@pytest.fixture
def setup_account():
    store = InMemoryAccountStore()
    recommender = FakeRecommender()
    app = create_app(
        settings=Settings(), analyzer=FakeAnalyzer(), recommender=recommender,
        account_store=store,
    )
    return TestClient(app), store, recommender


def signup(client: TestClient, username="alice", ids=None):
    return client.post("/api/auth/signup", headers=HEADERS, json={
        "username": username, "password": PASSWORD, "favorite_ids": ids or [],
    })


def test_signup_imports_guest_favorites_and_opens_safe_session(setup_account):
    client, store, _ = setup_account
    response = signup(client, " Alice ", [603, 550, 603])

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["username"] == "alice"
    assert data["favorite_ids"] == [603, 550]
    assert set(data["user"]) == {"id", "username", "created_at"}
    assert client.get("/api/auth/me").json() == data
    assert client.get("/api/favorites").json() == {"ids": [603, 550]}
    user = store.find_user("alice")
    assert {field.name for field in fields(User)} == {"id", "username", "password_hash", "created_at"}
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api" in cookie and "max-age=86400" in cookie
    token = client.cookies.get(SESSION_COOKIE)
    assert token not in store._sessions
    assert hashlib.sha256(token.encode()).hexdigest() in store._sessions


def test_username_is_unique_without_case_and_failed_signup_keeps_account(setup_account):
    client, store, _ = setup_account
    signup(client, "alice", [1])
    response = signup(client, "ALICE", [2])
    assert response.status_code == 409
    assert len(store._users) == 1
    assert client.get("/api/favorites").json()["ids"] == [1]


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": PASSWORD},
    {"username": "nom avec espaces", "password": PASSWORD},
    {"username": "alice", "password": "short"},
    {"username": "alice", "password": PASSWORD, "favorite_ids": [0]},
    {"username": "alice", "password": PASSWORD, "favorite_ids": list(range(1, 22))},
    {"username": "alice", "password": PASSWORD, "user_id": "someone-else"},
])
def test_invalid_signup_creates_no_account(setup_account, body):
    client, store, _ = setup_account
    assert client.post("/api/auth/signup", json=body, headers=HEADERS).status_code == 422
    assert store._users == {}


def test_login_rotates_token_and_logout_revokes_it(setup_account):
    client, store, _ = setup_account
    signup(client, ids=[7])
    old_token = client.cookies.get(SESSION_COOKIE)
    response = client.post("/api/auth/login", headers=HEADERS, json={
        "username": "ALICE", "password": PASSWORD,
    })
    assert response.status_code == 200
    token = client.cookies.get(SESSION_COOKIE)
    assert token != old_token
    assert store.session_user(hashlib.sha256(old_token.encode()).hexdigest()) is None
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
    assert client.get("/api/auth/me").json()["user"] is None
    assert client.get("/api/favorites").status_code == 401
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/favorites").status_code == 401


def test_login_errors_are_generic_and_do_not_replace_valid_session(setup_account):
    client, _, _ = setup_account
    signup(client)
    token = client.cookies.get(SESSION_COOKIE)
    wrong = client.post("/api/auth/login", headers=HEADERS, json={"username": "alice", "password": "wrong"})
    missing = client.post("/api/auth/login", headers=HEADERS, json={"username": "unknown", "password": "wrong"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    assert client.cookies.get(SESSION_COOKIE) == token


def test_favorites_are_isolated_idempotent_and_used_for_recommendations(setup_account):
    client, _, recommender = setup_account
    alice = signup(client, "alice", [1]).json()["user"]
    assert client.put("/api/favorites/2", headers=HEADERS).json()["ids"] == [1, 2]
    assert client.put("/api/favorites/2", headers=HEADERS).json()["ids"] == [1, 2]
    client.post("/api/recommendations", json={"message": "Un thriller", "favorite_ids": [999]})
    assert recommender.favorite_ids == [1, 2]
    client.post("/api/auth/logout", headers=HEADERS)
    signup(client, "bob", [3])
    assert client.get("/api/favorites").json()["ids"] == [3]
    stale_headers = {**HEADERS, "X-MovieMatch-User": alice["id"]}
    assert client.put("/api/favorites/4", headers=stale_headers).status_code == 401
    assert client.post("/api/auth/logout", headers=stale_headers).status_code == 401
    assert client.post("/api/recommendations", headers=stale_headers,
                       json={"message": "Un thriller"}).status_code == 401
    client.post("/api/auth/login", headers=HEADERS, json={"username": "alice", "password": PASSWORD})
    assert client.delete("/api/favorites/1", headers=HEADERS).json()["ids"] == [2]
    assert client.delete("/api/favorites/1", headers=HEADERS).json()["ids"] == [2]


def test_favorite_limit_and_missing_auth_are_enforced(setup_account):
    client, _, _ = setup_account
    assert client.put("/api/favorites/1", headers=HEADERS).status_code == 401
    assert client.delete("/api/favorites/1", headers=HEADERS).status_code == 401
    signup(client, ids=list(range(1, 21)))
    assert client.put("/api/favorites/21", headers=HEADERS).status_code == 409
    assert client.put("/api/favorites/20", headers=HEADERS).status_code == 200
    assert client.put("/api/favorites/0", headers=HEADERS).status_code == 422


def test_csrf_protection_on_auth_and_favorite_mutations(setup_account):
    client, _, _ = setup_account
    body = {"username": "alice", "password": PASSWORD}
    assert client.post("/api/auth/signup", json=body).status_code == 403
    evil = {"X-MovieMatch-Request": "1", "Origin": "https://evil.example"}
    assert client.post("/api/auth/signup", headers=evil, json=body).status_code == 403
    signup(client)
    for method, path, json in [
        ("POST", "/api/auth/login", body),
        ("POST", "/api/auth/logout", None),
        ("PUT", "/api/favorites/1", None),
        ("DELETE", "/api/favorites/1", None),
    ]:
        assert client.request(method, path, json=json).status_code == 403
        assert client.request(method, path, headers=evil, json=json).status_code == 403
    preflight = client.options("/api/auth/login", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-MovieMatch-Request",
    })
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_expired_and_forged_tokens_are_rejected(setup_account):
    client, store, _ = setup_account
    signup(client)
    token = client.cookies.get(SESSION_COOKIE)
    digest = hashlib.sha256(token.encode()).hexdigest()
    user = store.find_user("alice")
    store.create_session(digest, user.id, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert client.get("/api/favorites").status_code == 401
    assert digest not in store._sessions
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, "forged-token")
    assert client.get("/api/favorites").status_code == 401


def test_login_attempts_are_limited(setup_account):
    client, _, _ = setup_account
    for _ in range(10):
        assert client.post("/api/auth/login", headers=HEADERS, json={
            "username": "unknown", "password": "wrong",
        }).status_code == 401
    assert client.post("/api/auth/login", headers=HEADERS, json={
        "username": "unknown", "password": "wrong",
    }).status_code == 429


def test_secure_cookie_over_https_and_fresh_store_after_restart():
    settings = Settings(auth_cookie_secure=True)
    app = create_app(settings, FakeAnalyzer(), FakeRecommender())
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/auth/signup", headers={
        "X-MovieMatch-Request": "1", "Origin": "https://testserver",
    }, json={"username": "alice", "password": PASSWORD})
    assert response.status_code == 201
    assert "secure" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["user"]["username"] == "alice"
    restarted = TestClient(create_app(settings, FakeAnalyzer(), FakeRecommender()), base_url="https://testserver")
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/auth/me").json()["user"] is None


@pytest.mark.asyncio
async def test_concurrent_signup_cannot_create_duplicate_username():
    store = InMemoryAccountStore()
    app = create_app(Settings(), FakeAnalyzer(), FakeRecommender(), store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        responses = await asyncio.gather(*[
            client.post("/api/auth/signup", headers=HEADERS, json={"username": "alice", "password": PASSWORD})
            for _ in range(2)
        ])
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert len(store._users) == 1
