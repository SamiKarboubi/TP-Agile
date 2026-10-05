from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app.core.config import Settings
from app.services.account_store import User


class PostgresAccountStore:
    """Each operation owns a short connection and transaction, closed on exit."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect(self) -> psycopg.Connection:
        password = self._settings.db_password.get_secret_value()
        if not password:
            raise ValueError("DB_PASSWORD doit être renseigné dans backend/.env.")
        return psycopg.connect(
            host=self._settings.db_host,
            port=self._settings.db_port,
            dbname=self._settings.db_name,
            user=self._settings.db_user,
            password=password,
            connect_timeout=self._settings.db_connect_timeout_seconds,
            row_factory=dict_row,
            options="-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=5000",
        )

    def initialize(self) -> None:
        schema = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
        with self._connect() as connection:
            # Serialize bootstrap if several backend processes start together.
            connection.execute("SELECT pg_advisory_xact_lock(73491205)")
            connection.execute(schema.read_text(encoding="utf-8"))

    def check_health(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1 FROM users LIMIT 1")

    @staticmethod
    def _user(row: dict | None) -> User | None:
        return User(str(row["id"]), row["username"], row["password_hash"], row["created_at"]) if row else None

    @staticmethod
    def _favorite_ids(connection: psycopg.Connection, user_id: str) -> list[int]:
        rows = connection.execute(
            "SELECT movie_id FROM favorites WHERE user_id = %s ORDER BY position", (user_id,),
        ).fetchall()
        return [row["movie_id"] for row in rows]

    @staticmethod
    def _lock_user(connection: psycopg.Connection, user_id: str) -> None:
        # Concurrent tabs/processes cannot exceed the favorite limit or reorder writes.
        row = connection.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,)).fetchone()
        if row is None:
            raise ValueError("Ce compte n'existe plus.")

    def find_user(self, username: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = %s",
                (username,),
            ).fetchone()
            return self._user(row)

    def create_user(self, username: str, password_hash: str, favorite_ids: list[int]) -> User:
        ids = list(dict.fromkeys(favorite_ids))
        if len(ids) > 20:
            raise ValueError("La limite de 20 favoris est atteinte.")
        user = User(str(uuid4()), username, password_hash, datetime.now(timezone.utc))
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (id, username, password_hash, created_at) VALUES (%s, %s, %s, %s)",
                    (user.id, user.username, user.password_hash, user.created_at),
                )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO favorites (user_id, movie_id) VALUES (%s, %s)",
                        [(user.id, movie_id) for movie_id in ids],
                    )
        except UniqueViolation:
            raise ValueError("Ce nom d'utilisateur est déjà utilisé.") from None
        return user

    def create_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP")
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (token_hash) DO UPDATE SET user_id = EXCLUDED.user_id, expires_at = EXCLUDED.expires_at",
                (token_hash, user_id, expires_at),
            )

    def session_user(self, token_hash: str) -> User | None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = %s AND expires_at <= CURRENT_TIMESTAMP", (token_hash,),
            )
            row = connection.execute(
                "SELECT u.id, u.username, u.password_hash, u.created_at FROM sessions s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > CURRENT_TIMESTAMP", (token_hash,),
            ).fetchone()
            return self._user(row)

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def favorite_ids(self, user_id: str) -> list[int]:
        with self._connect() as connection:
            return self._favorite_ids(connection, user_id)

    def add_favorite(self, user_id: str, movie_id: int) -> list[int]:
        with self._connect() as connection:
            self._lock_user(connection, user_id)
            ids = self._favorite_ids(connection, user_id)
            if movie_id not in ids:
                if len(ids) >= 20:
                    raise ValueError("La limite de 20 favoris est atteinte.")
                connection.execute("INSERT INTO favorites (user_id, movie_id) VALUES (%s, %s)", (user_id, movie_id))
                ids.append(movie_id)
            return ids

    def remove_favorite(self, user_id: str, movie_id: int) -> list[int]:
        with self._connect() as connection:
            self._lock_user(connection, user_id)
            connection.execute("DELETE FROM favorites WHERE user_id = %s AND movie_id = %s", (user_id, movie_id))
            return self._favorite_ids(connection, user_id)
