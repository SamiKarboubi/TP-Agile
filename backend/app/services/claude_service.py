from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
)

from app.core.config import Settings
from app.schemas.intents import MovieSearchIntent
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
- Preserve person, title, genre, keyword, company and provider names verbatim; never invent ids.
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
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key or "missing",
            timeout=settings.anthropic_timeout_seconds,
            max_retries=settings.anthropic_max_retries,
        )

    async def analyze(self, message: str) -> MovieSearchIntent:
        if not self._settings.anthropic_api_key:
            raise ServiceConfigurationError("ANTHROPIC_API_KEY n’est pas configurée.")

        try:
            response = await self._client.messages.parse(
                model=self._settings.anthropic_model,
                max_tokens=1800,
                system=INTENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message}],
                output_format=MovieSearchIntent,
            )
        except AuthenticationError as exc:
            raise ServiceConfigurationError("La clé Anthropic est invalide.") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ClaudeServiceError("Claude est temporairement indisponible.") from exc
        except APIStatusError as exc:
            raise ClaudeServiceError("Claude n’a pas pu analyser la demande.") from exc
        except (TypeError, ValueError) as exc:
            raise ClaudeServiceError("Claude a renvoyé une analyse invalide.") from exc

        if response.parsed_output is None:
            raise ClaudeServiceError("Claude a renvoyé une analyse vide ou invalide.")
        return response.parsed_output

