"""Real PostgreSQL tests: opt in with TEST_DB_PASSWORD; CI always runs them."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import IntegrityError, OperationalError, sql
import pytest

from app.api.accounts import SESSION_COOKIE
from app.core.config import Settings
from app.main import create_app
from app.services.postgres_account_store import PostgresAccountStore
from test_main import FakeAnalyzer, FakeRecommender


HEADERS = {"X-MovieMatch-Request": "1", "Origin": "http://testserver"}
PASSWORD = "Abcdef1!"


@pytest.fixture
def store():
    password = os.environ.get("TEST_DB_PASSWORD")
    if not password:
        pytest.skip("Set TEST_DB_PASSWORD to run PostgreSQL integration tests")
    settings = Settings(
        _env_file=None,
        db_host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        db_port=int(os.environ.get("TEST_DB_PORT", "5432")),
        db_name=os.environ.get("TEST_DB_NAME", "moviematch_test"),
        db_user=os.environ.get("TEST_DB_USER", "moviematch_test"),
        db_password=password,
    )
    schema_name = "test_" + uuid4().hex
    base = PostgresAccountStore(settings)
    with base._connect() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))

    class IsolatedStore(PostgresAccountStore):
        def _connect(self):
            connection = super()._connect()
            connection.execute("SELECT set_config('search_path', %s, false)", (schema_name,))
            return connection

    isolated = IsolatedStore(settings)
    try:
        isolated.initialize()
        yield isolated
    finally:
        # Only this test's randomly named schema is removed, never existing tables.
        with base._connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name)))


def app_for(store):
    return create_app(Settings(_env_file=None), FakeAnalyzer(), FakeRecommender(), store)


def signup(client, username="alice", ids=None):
    return client.post("/api/auth/signup", headers=HEADERS, json={
        "username": username, "password": PASSWORD, "favorite_ids": ids or [],
    })


def test_signup_favorites_and_session_survive_app_restart(store):
    with TestClient(app_for(store)) as client:
        response = signup(client, " Alice ", [603, 550, 603])
        assert response.status_code == 201
        assert response.json()["favorite_ids"] == [603, 550]
        token = client.cookies.get(SESSION_COOKIE)
        user = response.json()["user"]
        assert client.put("/api/favorites/7", headers=HEADERS).json()["ids"] == [603, 550, 7]
        with store._connect() as connection:
            row = connection.execute("SELECT * FROM users").fetchone()
            assert set(row) == {"id", "username", "password_hash", "created_at"}
            assert row["password_hash"].startswith("$argon2id$")
            session = connection.execute("SELECT * FROM sessions").fetchone()
            assert session["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
            assert token not in str(session)
    # New app and new store object, using the same database/schema.
    restarted_store = type(store)(store._settings)
    with TestClient(app_for(restarted_store)) as restarted:
        restarted.cookies.set(SESSION_COOKIE, token)
        assert restarted.get("/api/auth/me").json() == {"user": user, "favorite_ids": [603, 550, 7]}
        assert restarted.post("/api/auth/logout", headers=HEADERS).status_code == 204
        restarted.cookies.set(SESSION_COOKIE, token)
        assert restarted.get("/api/favorites").status_code == 401
        assert restarted.post("/api/auth/login", headers=HEADERS, json={
            "username": "ALICE", "password": PASSWORD,
        }).status_code == 200


def test_login_wrong_short_password_and_favorite_isolation(store):
    with TestClient(app_for(store)) as client:
        alice = signup(client, ids=[1]).json()["user"]
        token = client.cookies.get(SESSION_COOKIE)
        wrong = client.post("/api/auth/login", headers=HEADERS, json={"username": "alice", "password": "x"})
        assert wrong.status_code == 401
        assert client.cookies.get(SESSION_COOKIE) == token
        assert signup(client, "ALICE", [2]).status_code == 409
        assert client.get("/api/favorites").json()["ids"] == [1]
        assert signup(client, "bob", [3]).status_code == 201
        assert client.put("/api/favorites/4", headers={**HEADERS, "X-MovieMatch-User": alice["id"]}).status_code == 401
        assert client.get("/api/favorites").json()["ids"] == [3]


def test_signup_import_rolls_back_on_invalid_favorite(store):
    with pytest.raises(IntegrityError):
        store.create_user("alice", "hash", [1, 0])
    assert store.find_user("alice") is None
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM favorites").fetchone()["n"] == 0


def test_concurrent_signups_enforce_unique_username(store):
    def create(_):
        try:
            store.create_user("alice", "hash", [1])
            return "created"
        except ValueError:
            return "duplicate"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(create, range(2))) == ["created", "duplicate"]
    assert store.favorite_ids(store.find_user("alice").id) == [1]


def test_concurrent_favorites_enforce_limit_and_order(store):
    user = store.create_user("alice", "hash", list(range(1, 20)))
    def add(movie_id):
        try:
            return store.add_favorite(user.id, movie_id)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(add, range(20, 24)))
    assert sum(result is not None for result in results) == 1
    ids = store.favorite_ids(user.id)
    assert len(ids) == 20 and ids[:19] == list(range(1, 20))
    assert store.add_favorite(user.id, ids[-1]) == ids
    assert store.remove_favorite(user.id, 1) == ids[1:]
    assert store.remove_favorite(user.id, 1) == ids[1:]
    assert store.add_favorite(user.id, 1) == ids[1:] + [1]


def test_expired_and_forged_sessions_are_rejected(store):
    user = store.create_user("alice", "hash", [])
    digest = hashlib.sha256(b"expired").hexdigest()
    store.create_session(digest, user.id, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert store.session_user(digest) is None
    assert store.session_user(hashlib.sha256(b"forged").hexdigest()) is None
    with store._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM sessions").fetchone()["n"] == 0


def test_schema_initialization_is_idempotent_and_foreign_keys_cascade(store):
    user = store.create_user("alice", "hash", [1])
    store.create_session("a" * 64, user.id, datetime.now(timezone.utc) + timedelta(hours=1))
    store.initialize()
    assert store.favorite_ids(user.id) == [1]
    with store._connect() as connection:
        connection.execute("DELETE FROM users WHERE id = %s", (user.id,))
    assert store.favorite_ids(user.id) == []
    assert store.session_user("a" * 64) is None


def test_database_outage_returns_503_without_connection_details():
    class UnavailableStore(PostgresAccountStore):
        def _connect(self):
            raise OperationalError("private connection details")
    app = app_for(UnavailableStore(Settings(_env_file=None)))
    # Without a lifespan, deliberately simulate a database lost after startup.
    client = TestClient(app, raise_server_exceptions=False)
    for path in ["/health", "/api/auth/me"]:
        client.cookies.set(SESSION_COOKIE, "any-token")
        response = client.get(path)
        assert response.status_code == 503
        assert "private" not in response.text


def test_missing_database_password_fails_startup_instead_of_using_memory():
    with pytest.raises(ValueError, match="DB_PASSWORD"):
        with TestClient(create_app(Settings(_env_file=None), FakeAnalyzer(), FakeRecommender())):
            pass
