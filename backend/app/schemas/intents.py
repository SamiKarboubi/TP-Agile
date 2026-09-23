from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _require_all_properties(schema: dict) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)


class IntRange(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    minimum: int | None = None
    maximum: int | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True


class FloatRange(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    minimum: float | None = Field(default=None, ge=0, le=10)
    maximum: float | None = Field(default=None, ge=0, le=10)
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True


class MovieConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    genres: list[str] = Field(default_factory=list)
    excluded_genres: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    similar_to: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    watch_providers: list[str] = Field(default_factory=list)
    watch_region: str | None = None
    year: IntRange = Field(default_factory=IntRange)
    runtime_minutes: IntRange = Field(default_factory=IntRange)
    imdb_rating: FloatRange = Field(default_factory=FloatRange)
    tmdb_rating: FloatRange = Field(default_factory=FloatRange)


class SortPreference(str, Enum):
    relevance = "relevance"
    popularity = "popularity"
    tmdb_rating = "tmdb_rating"
    imdb_rating = "imdb_rating"
    newest = "newest"
    oldest = "oldest"


class MovieSearchIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    is_movie_request: bool = Field(
        description="True only for movie search, recommendation, or decision-support requests."
    )
    required: MovieConstraints
    preferred: MovieConstraints
    sort_preference: SortPreference = SortPreference.relevance
    quality_requested: bool = Field(
        description="True when the user asks for a good, acclaimed, or well-rated movie."
    )
    classification_reason: str = Field(
        description="A short reason for the in-scope/out-of-scope classification."
    )
