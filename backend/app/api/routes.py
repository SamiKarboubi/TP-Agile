import asyncio
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request, Response
from app.api.accounts import SESSION_COOKIE
from app.services.auth_service import AuthService

from app.core.config import Settings
from app.core.constants import OUT_OF_SCOPE_MESSAGE
from app.schemas.intents import MovieSearchIntent
from app.schemas.recommendations import (
    MovieLookupRequest,
    MovieLookupResponse,
    MovieResult,
    PublicConfigResponse,
    RecommendationRequest,
    RecommendationResponse,
)


class IntentAnalyzer(Protocol):
    async def analyze(self, message: str) -> MovieSearchIntent: ...


class Recommender(Protocol):
    async def recommend(
        self, intent: MovieSearchIntent, favorite_ids: list[int] | None = None
    ) -> RecommendationResponse: ...

    async def lookup_movies(self, ids: list[int]) -> list[MovieResult]: ...
    async def random_movies(self) -> list[MovieResult]: ...


def build_router(
    settings: Settings,
    analyzer: IntentAnalyzer,
    recommender: Recommender,
    auth: AuthService,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/config", response_model=PublicConfigResponse)
    async def public_config() -> PublicConfigResponse:
        return PublicConfigResponse(max_user_message_length=settings.max_user_message_length)

    @router.post("/recommendations", response_model=RecommendationResponse)
    async def recommendations(request: RecommendationRequest, http_request: Request) -> RecommendationResponse:
        if len(request.message) > settings.max_user_message_length:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Le message dépasse la limite de "
                    f"{settings.max_user_message_length} caractères."
                ),
            )

        user = await asyncio.to_thread(auth.current_user, http_request.cookies.get(SESSION_COOKIE))
        expected = http_request.headers.get("X-MovieMatch-User")
        if expected is not None and (user is None or expected != user.id):
            raise HTTPException(401, "Votre session a expiré ou le compte connecté a changé.")
        intent = await analyzer.analyze(request.message)
        if not intent.is_movie_request:
            return RecommendationResponse(message=OUT_OF_SCOPE_MESSAGE, movies=[])
        favorite_ids = await asyncio.to_thread(auth.store.favorite_ids, user.id) if user else list(dict.fromkeys(request.favorite_ids))
        return await recommender.recommend(intent, favorite_ids)

    @router.get("/movies/random", response_model=MovieLookupResponse)
    async def random_movies(response: Response) -> MovieLookupResponse:
        response.headers["Cache-Control"] = "no-store"
        return MovieLookupResponse(movies=await recommender.random_movies())

    @router.post("/movies/lookup", response_model=MovieLookupResponse)
    async def lookup_movies(request: MovieLookupRequest) -> MovieLookupResponse:
        movies = await recommender.lookup_movies(list(dict.fromkeys(request.ids)))
        return MovieLookupResponse(movies=movies)

    return router
