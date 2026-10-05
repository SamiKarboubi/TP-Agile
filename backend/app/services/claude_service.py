from enum import Enum
import json

from pydantic import Field, create_model
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
)

from app.core.config import Settings
from app.schemas.intents import MovieConstraints, MovieSearchIntent
from app.services.genre_catalog import GenreCatalog
from app.services.errors import ClaudeServiceError, ServiceConfigurationError


INTENT_SYSTEM_PROMPT = """You classify and parse requests for a movie-only recommendation app.
Return the MovieSearchIntent structure and nothing else.

Scope:
- In scope: movie search/recommendation, movie constraints, actors/directors used to find movies,
  similar movies, and facts needed to choose a movie.
- Out of scope: TV-only requests and every unrelated topic.

Extraction rules:
- Put explicit must/with/without/minimum/maximum constraints in `required`.
- Put wishes introduced by words like preferably/ideally/de préférence in `preferred`.
- Preserve person, title, keyword, company and provider names verbatim; never invent ids.
- Genres MUST use the exact names from the supplied MCP genre catalog, in required AND preferred,
  including excluded_genres. Classify the user's meaning into zero, one or several catalog genres.
- Use [] if no genre is requested. Do not guess genres from actors, titles or "a good movie".
- Map clear genre synonyms to catalog names: "un film qui fait peur" => Horreur, "SF" => Science-Fiction,
  "un film drôle" => Comédie, only if these names exist in the supplied catalog.
- Do not turn themes or adjectives into invented genres (psychologique, spatial, français, etc.).
  Use keywords when appropriate, never an invented genre. Do not invent unsupported fields.
- Several REQUIRED genres mean the film must contain ALL of them; do not add unnecessary genres.
- "sans horreur" means excluded_genres=["Horreur"], not genres=["Horreur"].
- Convert hours to minutes.
- Preserve strict inequalities with the inclusive flags. Example: "after 2010" is minimum=2010,
  minimum_inclusive=false; "less than 2 hours" is maximum=120, maximum_inclusive=false.
- IMDb constraints go only in imdb_rating. Never copy them into tmdb_rating.
- TMDB constraints go only in tmdb_rating when TMDB is explicitly named.
- "well rated" or "a good movie" sets quality_requested=true but does not invent a numeric rating.
- "in the style of X" and "similar to X" go in similar_to.
- If no sort is stated, use relevance. Use imdb_rating only when IMDb ranking is requested.
- Every absent list is [], every absent range bound is null, and inclusive flags default to true.
- classification_reason is one short sentence and must not answer the user's request.
"""


class ClaudeService:
    def __init__(self, settings: Settings, genres: GenreCatalog) -> None:
        self._settings = settings
        self._genres = genres
        self._intent_model = None
        self._system_prompt = INTENT_SYSTEM_PROMPT
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key or "missing",
            timeout=settings.anthropic_timeout_seconds,
            max_retries=settings.anthropic_max_retries,
        )

    async def analyze(self, message: str) -> MovieSearchIntent:
        if not self._settings.anthropic_api_key:
            raise ServiceConfigurationError("ANTHROPIC_API_KEY n’est pas configurée.")

        if self._intent_model is None:
            catalog = await self._genres.get()
            names = [genre.name for genre in catalog]
            genre_enum = Enum("AvailableMovieGenre", {f"genre_{genre.id}": genre.name for genre in catalog}, type=str)
            constraints = create_model(
                "CatalogMovieConstraints", __base__=MovieConstraints,
                genres=(list[genre_enum], Field(default_factory=list)),
                excluded_genres=(list[genre_enum], Field(default_factory=list)),
            )
            self._intent_model = create_model(
                "CatalogMovieSearchIntent", __base__=MovieSearchIntent,
                required=(constraints, ...), preferred=(constraints, ...),
            )
            self._system_prompt = INTENT_SYSTEM_PROMPT + "\nAvailable MCP movie genres: " + json.dumps(names, ensure_ascii=False)

        try:
            response = await self._client.messages.parse(
                model=self._settings.anthropic_model,
                max_tokens=1800,
                system=self._system_prompt,
                messages=[{"role": "user", "content": message}],
                output_format=self._intent_model,
            )
            if response.parsed_output is None:
                raise ClaudeServiceError("Claude a renvoyé une analyse vide ou invalide.")
            validated = self._intent_model.model_validate(response.parsed_output.model_dump())
            intent = MovieSearchIntent.model_validate(validated.model_dump(mode="json"))
            for constraint in (intent.required, intent.preferred):
                constraint.genres = list(dict.fromkeys(constraint.genres))
                constraint.excluded_genres = list(dict.fromkeys(constraint.excluded_genres))
            return intent
        except AuthenticationError as exc:
            raise ServiceConfigurationError("La clé Anthropic est invalide.") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ClaudeServiceError("Claude est temporairement indisponible.") from exc
        except APIStatusError as exc:
            raise ClaudeServiceError("Claude n’a pas pu analyser la demande.") from exc
        except (TypeError, ValueError) as exc:
            raise ClaudeServiceError("Claude a renvoyé une analyse invalide.") from exc
