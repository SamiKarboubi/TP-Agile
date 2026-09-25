from typing import Protocol

from fastapi import APIRouter, HTTPException

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
    async def recommend(self, intent: MovieSearchIntent) -> RecommendationResponse: ...

    async def lookup_movies(self, ids: list[int]) -> list[MovieResult]: ...


def build_router(
    settings: Settings,
    analyzer: IntentAnalyzer,
    recommender: Recommender,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/config", response_model=PublicConfigResponse)
    async def public_config() -> PublicConfigResponse:
        return PublicConfigResponse(max_user_message_length=settings.max_user_message_length)

    @router.post("/recommendations", response_model=RecommendationResponse)
    async def recommendations(request: RecommendationRequest) -> RecommendationResponse:
        if len(request.message) > settings.max_user_message_length:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Le message dépasse la limite de "
                    f"{settings.max_user_message_length} caractères."
                ),
            )

        intent = await analyzer.analyze(request.message)
        if not intent.is_movie_request:
            return RecommendationResponse(message=OUT_OF_SCOPE_MESSAGE, movies=[])
        return await recommender.recommend(intent)

    @router.post("/movies/lookup", response_model=MovieLookupResponse)
    async def lookup_movies(request: MovieLookupRequest) -> MovieLookupResponse:
        movies = await recommender.lookup_movies(list(dict.fromkeys(request.ids)))
        return MovieLookupResponse(movies=movies)

    return router
