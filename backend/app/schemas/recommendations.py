from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class MovieResult(BaseModel):
    id: int
    title: str
    year: int | None = None
    poster_url: str | None = None
    overview: str | None = None
    runtime: int | None = None
    genres: list[str] = Field(default_factory=list)
    director: str | None = None
    main_cast: list[str] = Field(default_factory=list)
    tmdb_rating: float | None = None
    imdb_rating: float | None = None
    rotten_tomatoes: str | None = None
    metacritic: str | None = None
    tmdb_url: str | None = None
    imdb_url: str | None = None


class RecommendationResponse(BaseModel):
    message: str
    movies: list[MovieResult] = Field(default_factory=list, max_length=5)


class PublicConfigResponse(BaseModel):
    max_user_message_length: int

