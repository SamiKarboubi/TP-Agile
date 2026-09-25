from typing import Any

import pytest

from app.core.config import Settings
from app.schemas.intents import IntRange, MovieConstraints, MovieSearchIntent
from app.services.movie_service import MovieRecommendationService
from app.services.errors import MCPServiceError


def intent(required: MovieConstraints | None = None) -> MovieSearchIntent:
    return MovieSearchIntent(
        is_movie_request=True,
        required=required or MovieConstraints(),
        preferred=MovieConstraints(),
        classification_reason="test",
        quality_requested=False,
    )


def detail(movie_id: int, runtime: int = 110) -> dict[str, Any]:
    return {
        "id": movie_id,
        "title": f"Film {movie_id}",
        "year": 2020,
        "poster_url": None,
        "overview": "Synopsis",
        "runtime_minutes": runtime,
        "genres": ["Thriller"],
        "vote_average": 8.0,
        "ratings": {"found": True, "imdb_rating": "8.1"},
        "tmdb_url": f"https://www.themoviedb.org/movie/{movie_id}",
        "imdb_url": None,
    }


class FakeMCP:
    def __init__(
        self,
        runtimes: dict[int, int] | None = None,
        actor_id: int | None = None,
        imdb_ratings: dict[int, float] | None = None,
    ) -> None:
        self.runtimes = runtimes or {}
        self.actor_id = actor_id
        self.imdb_ratings = imdb_ratings or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "search_people":
            return {"results": [{"id": 10, "name": arguments["query"]}]}
        if name == "discover_movies":
            return {"results": [{"id": movie_id} for movie_id in range(1, 8)]}
        if name == "get_movie":
            movie_id = arguments["id"]
            return detail(movie_id, self.runtimes.get(movie_id, 110))
        if name == "get_movies":
            return {
                "results": [
                    {
                        "id": movie_id,
                        "found": True,
                        "ratings": {
                            "found": True,
                            "imdb_rating": str(self.imdb_ratings.get(movie_id, 7.0)),
                        },
                    }
                    for movie_id in arguments["ids"]
                ]
            }
        if name == "get_movie_credits":
            cast = [{"id": self.actor_id, "name": "Actor"}] if self.actor_id else []
            return {"cast": cast, "crew": [{"id": 20, "name": "Director", "job": "Director"}]}
        if name == "get_watch_providers":
            return {"available": False, "region": arguments["region"], "available_regions": []}
        if name == "get_videos":
            return {"results": []}
        raise AssertionError(f"Unexpected tool: {name}")


@pytest.mark.asyncio
async def test_returns_at_most_five_movies_and_rechecks_runtime() -> None:
    mcp = FakeMCP(runtimes={1: 130})
    service = MovieRecommendationService(Settings(), mcp)
    required = MovieConstraints(
        runtime_minutes=IntRange(maximum=120, maximum_inclusive=False)
    )

    response = await service.recommend(intent(required))

    assert len(response.movies) == 5
    assert all(movie.id != 1 for movie in response.movies)


@pytest.mark.asyncio
async def test_required_actor_is_not_silently_ignored() -> None:
    mcp = FakeMCP(actor_id=99)
    service = MovieRecommendationService(Settings(), mcp)
    required = MovieConstraints(actors=["Leonardo DiCaprio"])

    response = await service.recommend(intent(required))

    assert response.movies == []
    discover_call = next(arguments for name, arguments in mcp.calls if name == "discover_movies")
    assert discover_call["with_cast"] == "10"


@pytest.mark.asyncio
async def test_imdb_constraint_is_filtered_from_omdb_ratings_not_tmdb_rating() -> None:
    mcp = FakeMCP(imdb_ratings={1: 7.4, 2: 8.0})
    service = MovieRecommendationService(Settings(omdb_api_key="test-key"), mcp)
    required = MovieConstraints(imdb_rating={"minimum": 7.5})

    response = await service.recommend(intent(required))

    assert [movie.id for movie in response.movies] == [2]
    discover_call = next(arguments for name, arguments in mcp.calls if name == "discover_movies")
    assert "min_rating" not in discover_call


@pytest.mark.asyncio
async def test_similar_movies_still_respect_required_keyword() -> None:
    class KeywordMCP(FakeMCP):
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((name, arguments))
            if name == "search_keywords":
                return {"results": [{"id": 42, "name": "space"}]}
            if name == "search_movies":
                return {"results": [{"id": 100, "title": "Interstellar"}]}
            if name == "get_movie_recommendations":
                return {"results": [{"id": 1}]}
            if name == "get_similar":
                return {"results": []}
            if name == "discover_movies":
                return {"results": [{"id": 2}]}
            return await super().call_tool(name, arguments)

    mcp = KeywordMCP()
    service = MovieRecommendationService(Settings(), mcp)

    response = await service.recommend(
        intent(MovieConstraints(similar_to=["Interstellar"], keywords=["space"]))
    )

    assert response.movies == []
    assert not any(name == "get_movie" for name, _ in mcp.calls)


@pytest.mark.asyncio
async def test_title_search_requires_exact_title() -> None:
    class FuzzyMCP(FakeMCP):
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((name, arguments))
            if name == "search_movies":
                return {"results": [{"id": 1, "title": "Interstellar Voyage"}]}
            return await super().call_tool(name, arguments)

    mcp = FuzzyMCP()
    response = await MovieRecommendationService(Settings(), mcp).recommend(
        intent(MovieConstraints(titles=["Interstellar"]))
    )

    assert response.movies == []


@pytest.mark.asyncio
async def test_watch_options_use_requested_region_and_also_check_trailer() -> None:
    class ProviderMCP(FakeMCP):
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if name == "get_watch_providers":
                self.calls.append((name, arguments))
                return {
                    "available": True,
                    "streaming": ["Netflix"],
                    "free": [], "ads": [], "rent": ["Apple TV"], "buy": [],
                }
            if name == "get_videos":
                self.calls.append((name, arguments))
                return {"results": [{
                    "type": "Trailer", "official": True,
                    "url": "https://www.youtube.com/watch?v=official",
                }]}
            return await super().call_tool(name, arguments)

    mcp = ProviderMCP()
    response = await MovieRecommendationService(Settings(), mcp).recommend(
        intent(MovieConstraints(watch_region="FR"))
    )

    assert response.movies[0].streaming == ["Netflix"]
    assert response.movies[0].rent == ["Apple TV"]
    assert response.movies[0].trailer_url == "https://www.youtube.com/watch?v=official"
    assert all(args["region"] == "FR" for name, args in mcp.calls if name == "get_watch_providers")
    assert len([name for name, _ in mcp.calls if name == "get_videos"]) == 5


@pytest.mark.asyncio
async def test_trailer_is_returned_when_no_watch_provider_is_known() -> None:
    class TrailerMCP(FakeMCP):
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if name == "get_videos":
                self.calls.append((name, arguments))
                return {"results": [
                    {"type": "Trailer", "official": False, "url": "https://www.youtube.com/watch?v=first"},
                    {"type": "Trailer", "official": True, "url": "https://www.youtube.com/watch?v=official"},
                ]}
            return await super().call_tool(name, arguments)

    response = await MovieRecommendationService(Settings(), TrailerMCP()).recommend(intent())

    assert response.movies[0].trailer_url == "https://www.youtube.com/watch?v=official"


@pytest.mark.asyncio
async def test_optional_availability_failure_keeps_recommendations() -> None:
    class UnavailableMCP(FakeMCP):
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if name in {"get_watch_providers", "get_videos"}:
                raise MCPServiceError("upstream unavailable")
            return await super().call_tool(name, arguments)

    response = await MovieRecommendationService(Settings(), UnavailableMCP()).recommend(intent())

    assert len(response.movies) == 5
    assert response.movies[0].streaming == []
    assert response.movies[0].trailer_url is None
