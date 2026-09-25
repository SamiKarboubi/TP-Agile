from dataclasses import dataclass, field
import re
from typing import Any, Protocol
import unicodedata
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.constants import NO_EXACT_MATCH_MESSAGE, RESULTS_MESSAGE
from app.schemas.intents import FloatRange, IntRange, MovieConstraints, MovieSearchIntent
from app.schemas.recommendations import MovieResult, RecommendationResponse
from app.services.errors import MCPServiceError, ServiceConfigurationError


class MovieDataClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ResolvedEntities:
    genre_ids: dict[str, int] = field(default_factory=dict)
    actor_ids: dict[str, int] = field(default_factory=dict)
    director_ids: dict[str, int] = field(default_factory=dict)
    keyword_ids: dict[str, int] = field(default_factory=dict)
    excluded_keyword_ids: dict[str, int] = field(default_factory=dict)
    company_ids: dict[str, int] = field(default_factory=dict)
    provider_ids: dict[str, int] = field(default_factory=dict)
    unresolved_required: list[str] = field(default_factory=list)


class MovieRecommendationService:
    def __init__(self, settings: Settings, mcp: MovieDataClient) -> None:
        self._settings = settings
        self._mcp = mcp

    async def recommend(self, intent: MovieSearchIntent) -> RecommendationResponse:
        if _has_bounds(intent.required.imdb_rating) and not self._settings.omdb_api_key:
            raise ServiceConfigurationError(
                "OMDB_API_KEY est nécessaire pour appliquer une contrainte IMDb."
            )

        resolved = await self._resolve_required_entities(intent.required)
        if resolved.unresolved_required:
            return RecommendationResponse(message=NO_EXACT_MATCH_MESSAGE, movies=[])

        candidates = await self._find_candidates(intent, resolved)
        candidates = _deduplicate(candidates)[: self._settings.movie_candidate_limit]
        if not candidates:
            return RecommendationResponse(message=NO_EXACT_MATCH_MESSAGE, movies=[])

        batch_ratings: dict[int, float | None] = {}
        needs_imdb_batch = (
            _has_bounds(intent.required.imdb_rating)
            or _has_bounds(intent.preferred.imdb_rating)
            or intent.sort_preference.value == "imdb_rating"
        )
        if needs_imdb_batch:
            batch_ratings = await self._get_batch_imdb_ratings(candidates)
            if _has_bounds(intent.required.imdb_rating):
                candidates = [
                    candidate
                    for candidate in candidates
                    if _range_contains(
                        intent.required.imdb_rating,
                        batch_ratings.get(int(candidate["id"])),
                    )
                ]
            if intent.sort_preference.value == "imdb_rating":
                candidates.sort(
                    key=lambda item: batch_ratings.get(int(item["id"])) or -1,
                    reverse=True,
                )

        movies: list[MovieResult] = []
        for candidate in candidates:
            movie_id = int(candidate["id"])
            detail = await self._mcp.call_tool(
                "get_movie",
                {
                    "id": movie_id,
                    "language": self._settings.tmdb_language,
                    "region": self._settings.tmdb_region,
                    "include_ratings": True,
                },
            )
            credits = await self._mcp.call_tool("get_movie_credits", {"id": movie_id})
            movie = _to_movie_result(detail, credits, batch_ratings.get(movie_id))
            if self._matches_required(movie, credits, intent.required, resolved):
                movies.append(movie)
            if len(movies) >= self._settings.max_recommendations:
                break

        watch_region = (
            intent.required.watch_region
            or intent.preferred.watch_region
            or self._settings.tmdb_region
        ).strip().upper()
        for movie in movies:
            try:
                providers = await self._mcp.call_tool(
                    "get_watch_providers",
                    {"media_type": "movie", "id": movie.id, "region": watch_region},
                )
            except MCPServiceError:
                providers = {}
            movie.watch_region = watch_region
            if providers.get("available") is True:
                for category in ("streaming", "free", "ads", "rent", "buy"):
                    names = providers.get(category)
                    if isinstance(names, list):
                        setattr(
                            movie,
                            category,
                            [name for name in names if isinstance(name, str) and name.strip()],
                        )

            try:
                videos = await self._mcp.call_tool(
                    "get_videos", {"media_type": "movie", "id": movie.id}
                )
            except MCPServiceError:
                videos = {}
            movie.trailer_url = _trailer_url(videos)

        return RecommendationResponse(
            message=RESULTS_MESSAGE if movies else NO_EXACT_MATCH_MESSAGE,
            movies=movies,
        )

    async def _resolve_required_entities(self, constraints: MovieConstraints) -> ResolvedEntities:
        resolved = ResolvedEntities()

        if constraints.genres or constraints.excluded_genres:
            payload = await self._mcp.call_tool("get_movie_genres", {})
            available = {
                _normalize_name(str(item.get("name", ""))): int(item["id"])
                for item in payload.get("genres", [])
                if item.get("id") is not None
            }
            for name in [*constraints.genres, *constraints.excluded_genres]:
                genre_id = available.get(_normalize_name(name))
                if genre_id is None:
                    resolved.unresolved_required.append(name)
                else:
                    resolved.genre_ids[_normalize_name(name)] = genre_id

        for name in constraints.actors:
            person_id = await self._resolve_named_id("search_people", name)
            if person_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.actor_ids[_normalize_name(name)] = person_id

        for name in constraints.directors:
            person_id = await self._resolve_named_id("search_people", name)
            if person_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.director_ids[_normalize_name(name)] = person_id

        for name in constraints.keywords:
            keyword_id = await self._resolve_named_id("search_keywords", name)
            if keyword_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.keyword_ids[_normalize_name(name)] = keyword_id

        for name in constraints.excluded_keywords:
            keyword_id = await self._resolve_named_id("search_keywords", name)
            if keyword_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.excluded_keyword_ids[_normalize_name(name)] = keyword_id

        for name in constraints.companies:
            company_id = await self._resolve_named_id("search_companies", name)
            if company_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.company_ids[_normalize_name(name)] = company_id

        watch_region = constraints.watch_region or self._settings.tmdb_region
        for name in constraints.watch_providers:
            provider_id = await self._resolve_named_id(
                "search_watch_providers",
                name,
                {"media_type": "movie", "watch_region": watch_region},
            )
            if provider_id is None:
                resolved.unresolved_required.append(name)
            else:
                resolved.provider_ids[_normalize_name(name)] = provider_id

        return resolved

    async def _resolve_named_id(
        self,
        tool: str,
        name: str,
        extra: dict[str, Any] | None = None,
    ) -> int | None:
        payload = await self._mcp.call_tool(tool, {"query": name, **(extra or {})})
        results = payload.get("results", [])
        if not isinstance(results, list) or not results:
            return None
        exact = next(
            (
                item
                for item in results
                if _normalize_name(
                    str(item.get("name") or item.get("title") or item.get("provider_name") or "")
                )
                == _normalize_name(name)
            ),
            results[0],
        )
        value = exact.get("id", exact.get("provider_id"))
        return int(value) if isinstance(value, int) else None

    async def _find_candidates(
        self,
        intent: MovieSearchIntent,
        resolved: ResolvedEntities,
    ) -> list[dict[str, Any]]:
        if intent.required.similar_to:
            groups = [
                await self._find_similar_candidates(title)
                for title in intent.required.similar_to
            ]
            candidates = _intersect_candidates(groups)
        elif intent.required.titles:
            candidates = await self._find_title_candidates(intent.required.titles)
        elif intent.preferred.similar_to:
            candidates = await self._find_similar_candidates(intent.preferred.similar_to[0])
        else:
            return await self._discover_candidates(intent, resolved)

        if _requires_discovery_crosscheck(intent.required):
            discovered = await self._discover_candidates(intent, resolved)
            allowed_ids = {item["id"] for item in discovered if isinstance(item.get("id"), int)}
            candidates = [item for item in candidates if item.get("id") in allowed_ids]
        return candidates

    async def _discover_candidates(
        self,
        intent: MovieSearchIntent,
        resolved: ResolvedEntities,
    ) -> list[dict[str, Any]]:
        payload = await self._mcp.call_tool(
            "discover_movies", self._discover_arguments(intent, resolved)
        )
        results = payload.get("results", [])
        return results if isinstance(results, list) else []

    async def _find_similar_candidates(self, title: str) -> list[dict[str, Any]]:
        source = await self._search_movie(title)
        if source is None:
            return []
        movie_id = int(source["id"])
        recommended = await self._mcp.call_tool(
            "get_movie_recommendations", {"id": movie_id, "page": 1}
        )
        results = list(recommended.get("results", []))
        if len(results) < self._settings.movie_candidate_limit:
            similar = await self._mcp.call_tool(
                "get_similar", {"media_type": "movie", "id": movie_id, "page": 1}
            )
            results.extend(similar.get("results", []))
        return results

    async def _find_title_candidates(self, titles: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for title in titles:
            match = await self._search_movie(title)
            if match is not None:
                results.append(match)
        return results

    async def _search_movie(self, title: str) -> dict[str, Any] | None:
        payload = await self._mcp.call_tool(
            "search_movies",
            {"query": title, "language": self._settings.tmdb_language, "page": 1},
        )
        results = payload.get("results", [])
        if not isinstance(results, list) or not results:
            return None
        return next(
            (
                item
                for item in results
                if _normalize_name(str(item.get("title") or "")) == _normalize_name(title)
                or _normalize_name(str(item.get("original_title") or ""))
                == _normalize_name(title)
            ),
            None,
        )

    def _discover_arguments(
        self,
        intent: MovieSearchIntent,
        resolved: ResolvedEntities,
    ) -> dict[str, Any]:
        constraints = intent.required
        args: dict[str, Any] = {
            "page": 1,
            "language": self._settings.tmdb_language,
            "include_adult": False,
            "sort_by": _tmdb_sort(intent),
        }
        included_genres = [resolved.genre_ids[_normalize_name(name)] for name in constraints.genres]
        excluded_genres = [
            resolved.genre_ids[_normalize_name(name)] for name in constraints.excluded_genres
        ]
        optional_values: dict[str, Any] = {
            "with_genres": _id_list(included_genres),
            "without_genres": _id_list(excluded_genres),
            "with_cast": _id_list(resolved.actor_ids.values()),
            "with_crew": _id_list(resolved.director_ids.values()),
            "with_keywords": _id_list(resolved.keyword_ids.values()),
            "without_keywords": _id_list(resolved.excluded_keyword_ids.values()),
            "with_companies": _id_list(resolved.company_ids.values()),
            "with_watch_providers": _id_list(resolved.provider_ids.values()),
        }
        args.update({key: value for key, value in optional_values.items() if value is not None})
        if resolved.provider_ids:
            args["watch_region"] = constraints.watch_region or self._settings.tmdb_region

        year_min = _integer_lower_bound(constraints.year)
        year_max = _integer_upper_bound(constraints.year)
        if year_min is not None:
            args["release_date_gte"] = f"{year_min:04d}-01-01"
        if year_max is not None:
            args["release_date_lte"] = f"{year_max:04d}-12-31"

        runtime_min = _integer_lower_bound(constraints.runtime_minutes)
        runtime_max = _integer_upper_bound(constraints.runtime_minutes)
        if runtime_min is not None:
            args["min_runtime"] = runtime_min
        if runtime_max is not None:
            args["max_runtime"] = runtime_max

        if constraints.tmdb_rating.minimum is not None:
            args["min_rating"] = constraints.tmdb_rating.minimum
        if constraints.tmdb_rating.maximum is not None:
            args["max_rating"] = constraints.tmdb_rating.maximum
        if intent.quality_requested or intent.sort_preference.value == "tmdb_rating":
            args["min_votes"] = self._settings.default_min_votes
        return args

    async def _get_batch_imdb_ratings(
        self, candidates: list[dict[str, Any]]
    ) -> dict[int, float | None]:
        payload = await self._mcp.call_tool(
            "get_movies",
            {
                "ids": [int(item["id"]) for item in candidates],
                "language": self._settings.tmdb_language,
                "include_ratings": True,
            },
        )
        ratings: dict[int, float | None] = {}
        failure_reasons: list[str] = []
        for item in payload.get("results", []):
            if not item.get("found", False):
                continue
            rating_data = item.get("ratings") or {}
            movie_id = int(item["id"])
            ratings[movie_id] = _parse_rating(rating_data.get("imdb_rating"))
            if not rating_data.get("found", False):
                failure_reasons.append(str(rating_data.get("reason", "")))

        if ratings and all(value is None for value in ratings.values()):
            if failure_reasons and all("lookup failed" in reason.lower() for reason in failure_reasons):
                raise MCPServiceError("OMDb est temporairement indisponible.")
        return ratings

    def _matches_required(
        self,
        movie: MovieResult,
        credits: dict[str, Any],
        constraints: MovieConstraints,
        resolved: ResolvedEntities,
    ) -> bool:
        genres = {_normalize_name(genre) for genre in movie.genres}
        if not {_normalize_name(genre) for genre in constraints.genres}.issubset(genres):
            return False
        if genres.intersection(_normalize_name(genre) for genre in constraints.excluded_genres):
            return False
        if not _range_contains(constraints.year, movie.year):
            return False
        if not _range_contains(constraints.runtime_minutes, movie.runtime):
            return False
        if not _range_contains(constraints.imdb_rating, movie.imdb_rating):
            return False
        if not _range_contains(constraints.tmdb_rating, movie.tmdb_rating):
            return False

        cast_ids = {item.get("id") for item in credits.get("cast", [])}
        if not set(resolved.actor_ids.values()).issubset(cast_ids):
            return False
        director_ids = {
            item.get("id")
            for item in credits.get("crew", [])
            if str(item.get("job", "")).casefold() == "director"
        }
        return set(resolved.director_ids.values()).issubset(director_ids)


def _to_movie_result(
    detail: dict[str, Any],
    credits: dict[str, Any],
    fallback_imdb_rating: float | None,
) -> MovieResult:
    cast = [str(item["name"]) for item in credits.get("cast", []) if item.get("name")][:5]
    directors = [
        str(item["name"])
        for item in credits.get("crew", [])
        if item.get("name") and str(item.get("job", "")).casefold() == "director"
    ]
    ratings = detail.get("ratings") or {}
    imdb_rating = _parse_rating(ratings.get("imdb_rating"))
    return MovieResult(
        id=int(detail["id"]),
        title=str(detail.get("title") or "Titre inconnu"),
        year=detail.get("year"),
        poster_url=detail.get("poster_url"),
        overview=detail.get("overview"),
        runtime=detail.get("runtime_minutes"),
        genres=[str(genre) for genre in detail.get("genres", [])],
        director=directors[0] if directors else None,
        main_cast=cast,
        tmdb_rating=detail.get("vote_average"),
        imdb_rating=imdb_rating if imdb_rating is not None else fallback_imdb_rating,
        rotten_tomatoes=ratings.get("rotten_tomatoes") if ratings.get("found") else None,
        metacritic=ratings.get("metascore") if ratings.get("found") else None,
        tmdb_url=detail.get("tmdb_url"),
        imdb_url=detail.get("imdb_url"),
    )


def _trusted_url(value: Any, hostname: str) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.hostname == hostname else None


def _trailer_url(payload: dict[str, Any]) -> str | None:
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    trailers = [
        item for item in results
        if isinstance(item, dict) and item.get("type") == "Trailer"
        and _trusted_url(item.get("url"), "www.youtube.com")
    ]
    trailers.sort(key=lambda item: item.get("official") is True, reverse=True)
    return _trusted_url(trailers[0]["url"], "www.youtube.com") if trailers else None


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        value = item.get("id")
        if not isinstance(value, int) or value in seen:
            continue
        seen.add(value)
        unique.append(item)
    return unique


def _intersect_candidates(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if not groups:
        return []
    common_ids = [
        {item["id"] for item in group if isinstance(item.get("id"), int)}
        for group in groups
    ]
    return [
        item
        for item in groups[0]
        if isinstance(item.get("id"), int)
        and all(item["id"] in ids for ids in common_ids[1:])
    ]


def _requires_discovery_crosscheck(constraints: MovieConstraints) -> bool:
    return bool(
        constraints.keywords
        or constraints.excluded_keywords
        or constraints.companies
        or constraints.watch_providers
    )


def _id_list(values: Any) -> str | None:
    items = [str(value) for value in values]
    return ",".join(items) if items else None


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    compact = re.sub(r"[^a-z0-9]+", "", ascii_value)
    return "sciencefiction" if compact in {"scifi", "sf"} else compact


def _has_bounds(value: IntRange | FloatRange) -> bool:
    return value.minimum is not None or value.maximum is not None


def _range_contains(value_range: IntRange | FloatRange, value: float | int | None) -> bool:
    if not _has_bounds(value_range):
        return True
    if value is None:
        return False
    if value_range.minimum is not None:
        if value < value_range.minimum or (
            value == value_range.minimum and not value_range.minimum_inclusive
        ):
            return False
    if value_range.maximum is not None:
        if value > value_range.maximum or (
            value == value_range.maximum and not value_range.maximum_inclusive
        ):
            return False
    return True


def _integer_lower_bound(value_range: IntRange) -> int | None:
    if value_range.minimum is None:
        return None
    return value_range.minimum if value_range.minimum_inclusive else value_range.minimum + 1


def _integer_upper_bound(value_range: IntRange) -> int | None:
    if value_range.maximum is None:
        return None
    return value_range.maximum if value_range.maximum_inclusive else value_range.maximum - 1


def _parse_rating(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tmdb_sort(intent: MovieSearchIntent) -> str:
    values = {
        "tmdb_rating": "vote_average.desc",
        "newest": "primary_release_date.desc",
        "oldest": "primary_release_date.asc",
        "popularity": "popularity.desc",
    }
    if intent.quality_requested:
        return "vote_average.desc"
    return values.get(intent.sort_preference.value, "popularity.desc")
