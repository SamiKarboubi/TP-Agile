import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from threading import Lock
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException

from app.core.config import Settings
from app.services.account_store import InMemoryAccountStore, User


class AuthService:
    def __init__(self, settings: Settings, store: InMemoryAccountStore) -> None:
        self.store = store
        self._settings = settings
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))
        self._attempts: dict[str, deque[float]] = {}
        self._attempt_lock = Lock()

    def limit_attempts(self, client: str) -> None:
        """At most ten login/signup attempts per client in a rolling minute."""
        now = time.monotonic()
        with self._attempt_lock:
            self._attempts = {
                key: attempts for key, attempts in self._attempts.items()
                if attempts and attempts[-1] > now - 60
            }
            attempts = self._attempts.setdefault(client, deque())
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 10:
                raise HTTPException(429, "Trop de tentatives. Réessayez dans une minute.")
            attempts.append(now)

    async def signup(self, username: str, password: str, favorite_ids: list[int]) -> User:
        password_hash = await asyncio.to_thread(self._hasher.hash, password)
        try:
            return self.store.create_user(username, password_hash, favorite_ids)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    async def login(self, username: str, password: str) -> User:
        user = self.store.find_user(username)
        try:
            await asyncio.to_thread(
                self._hasher.verify, user.password_hash if user else self._dummy_hash, password
            )
        except VerificationError:
            raise HTTPException(401, "Nom d'utilisateur ou mot de passe incorrect.") from None
        if user is None:
            raise HTTPException(401, "Nom d'utilisateur ou mot de passe incorrect.")
        return user

    def new_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self._settings.auth_session_hours)
        self.store.create_session(_token_hash(token), user.id, expires_at)
        return token

    def current_user(self, token: str | None) -> User | None:
        return self.store.session_user(_token_hash(token)) if token else None

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(_token_hash(token))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
