from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password_hash: str
    created_at: datetime


@dataclass(frozen=True)
class Session:
    user_id: str
    expires_at: datetime


class InMemoryAccountStore:
    """One app instance owns these dictionaries; restarting it clears them."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._usernames: dict[str, str] = {}
        self._sessions: dict[str, Session] = {}
        self._favorites: dict[str, list[int]] = {}
        self._lock = RLock()

    def find_user(self, username: str) -> User | None:
        with self._lock:
            user_id = self._usernames.get(username)
            return self._users.get(user_id) if user_id else None

    def create_user(self, username: str, password_hash: str, favorite_ids: list[int]) -> User:
        with self._lock:
            if username in self._usernames:
                raise ValueError("Ce nom d'utilisateur est déjà utilisé.")
            user = User(str(uuid4()), username, password_hash, datetime.now(timezone.utc))
            self._users[user.id] = user
            self._usernames[username] = user.id
            self._favorites[user.id] = list(dict.fromkeys(favorite_ids))
            return user

    def create_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        with self._lock:
            now = datetime.now(timezone.utc)
            self._sessions = {
                key: session for key, session in self._sessions.items()
                if session.expires_at > now
            }
            self._sessions[token_hash] = Session(user_id, expires_at)

    def session_user(self, token_hash: str) -> User | None:
        with self._lock:
            session = self._sessions.get(token_hash)
            if session is None:
                return None
            if session.expires_at <= datetime.now(timezone.utc):
                self._sessions.pop(token_hash, None)
                return None
            return self._users.get(session.user_id)

    def delete_session(self, token_hash: str) -> None:
        with self._lock:
            self._sessions.pop(token_hash, None)

    def favorite_ids(self, user_id: str) -> list[int]:
        with self._lock:
            return self._favorites[user_id].copy()

    def add_favorite(self, user_id: str, movie_id: int) -> list[int]:
        with self._lock:
            ids = self._favorites[user_id]
            if movie_id not in ids:
                if len(ids) >= 20:
                    raise ValueError("La limite de 20 favoris est atteinte.")
                ids.append(movie_id)
            return ids.copy()

    def remove_favorite(self, user_id: str, movie_id: int) -> list[int]:
        with self._lock:
            self._favorites[user_id] = [id_ for id_ in self._favorites[user_id] if id_ != movie_id]
            return self._favorites[user_id].copy()
