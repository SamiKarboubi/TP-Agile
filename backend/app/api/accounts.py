import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from app.core.config import Settings
from app.schemas.accounts import (
    AccountResponse, FavoritesResponse, LoginRequest, PublicUser, SignupRequest,
)
from app.services.account_store import User
from app.services.auth_service import AuthService


SESSION_COOKIE = "moviematch_session"


def build_account_router(settings: Settings, auth: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api")

    def protected_action(request: Request) -> None:
        # A cross-site HTML form cannot set this header; JS needs a CORS preflight.
        if request.headers.get("X-MovieMatch-Request") != "1":
            raise HTTPException(403, "Requête non autorisée.")
        origin = request.headers.get("origin")
        allowed = {*settings.allowed_origins, str(request.base_url).rstrip("/")}
        if origin is not None and origin not in allowed:
            raise HTTPException(403, "Origine non autorisée.")

    def require_user(request: Request) -> User:
        user = auth.current_user(request.cookies.get(SESSION_COOKIE))
        if user is None:
            raise HTTPException(401, "Connectez-vous pour accéder à vos favoris.")
        # Prevent an old tab from modifying a different account after another tab logs in.
        expected = request.headers.get("X-MovieMatch-User")
        if expected is not None and expected != user.id:
            raise HTTPException(401, "Le compte connecté a changé. Actualisez la page.")
        return user

    def account_response(user: User | None) -> AccountResponse:
        return AccountResponse(
            user=PublicUser(id=user.id, username=user.username, created_at=user.created_at)
            if user else None,
            favorite_ids=auth.store.favorite_ids(user.id) if user else [],
        )

    def open_session(request: Request, response: Response, user: User) -> None:
        auth.logout(request.cookies.get(SESSION_COOKIE))
        token = auth.new_session(user)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, secure=settings.auth_cookie_secure,
            samesite="lax", path="/api", max_age=settings.auth_session_hours * 3600,
        )
        response.headers["Cache-Control"] = "no-store"

    def limit_auth(request: Request) -> None:
        auth.limit_attempts(request.client.host if request.client else "unknown")

    @router.post("/auth/signup", response_model=AccountResponse, status_code=201,
                 dependencies=[Depends(protected_action), Depends(limit_auth)])
    async def signup(body: SignupRequest, request: Request, response: Response) -> AccountResponse:
        user = await auth.signup(body.username, body.password, body.favorite_ids)
        await asyncio.to_thread(open_session, request, response, user)
        return await asyncio.to_thread(account_response, user)

    @router.post("/auth/login", response_model=AccountResponse,
                 dependencies=[Depends(protected_action), Depends(limit_auth)])
    async def login(body: LoginRequest, request: Request, response: Response) -> AccountResponse:
        user = await auth.login(body.username, body.password)
        await asyncio.to_thread(open_session, request, response, user)
        return await asyncio.to_thread(account_response, user)

    @router.get("/auth/me", response_model=AccountResponse)
    def me(request: Request, response: Response) -> AccountResponse:
        response.headers["Cache-Control"] = "no-store"
        return account_response(auth.current_user(request.cookies.get(SESSION_COOKIE)))

    @router.post("/auth/logout", status_code=204, dependencies=[Depends(protected_action)])
    def logout(request: Request, response: Response) -> None:
        require_user(request)
        auth.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(
            SESSION_COOKIE, path="/api", httponly=True,
            secure=settings.auth_cookie_secure, samesite="lax",
        )

    @router.get("/favorites", response_model=FavoritesResponse)
    def favorites(response: Response, user: Annotated[User, Depends(require_user)]) -> FavoritesResponse:
        response.headers["Cache-Control"] = "no-store"
        return FavoritesResponse(ids=auth.store.favorite_ids(user.id))

    @router.put("/favorites/{movie_id}", response_model=FavoritesResponse,
                dependencies=[Depends(protected_action)])
    def add_favorite(
        movie_id: Annotated[int, Path(gt=0, le=9223372036854775807)], user: Annotated[User, Depends(require_user)],
    ) -> FavoritesResponse:
        try:
            return FavoritesResponse(ids=auth.store.add_favorite(user.id, movie_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.delete("/favorites/{movie_id}", response_model=FavoritesResponse,
                   dependencies=[Depends(protected_action)])
    def remove_favorite(
        movie_id: Annotated[int, Path(gt=0, le=9223372036854775807)], user: Annotated[User, Depends(require_user)],
    ) -> FavoritesResponse:
        return FavoritesResponse(ids=auth.store.remove_favorite(user.id, movie_id))

    return router
