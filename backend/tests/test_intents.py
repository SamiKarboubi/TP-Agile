import pytest

from app.schemas.intents import MovieSearchIntent


@pytest.mark.parametrize(
    ("required", "assertions"),
    [
        ({"genres": ["Thriller"]}, lambda c: c.genres == ["Thriller"]),
        ({"actors": ["Leonardo DiCaprio"]}, lambda c: c.actors == ["Leonardo DiCaprio"]),
        ({"directors": ["Christopher Nolan"]}, lambda c: c.directors == ["Christopher Nolan"]),
        (
            {"year": {"minimum": 2010, "minimum_inclusive": False}},
            lambda c: c.year.minimum == 2010 and not c.year.minimum_inclusive,
        ),
        (
            {"runtime_minutes": {"maximum": 120, "maximum_inclusive": False}},
            lambda c: c.runtime_minutes.maximum == 120 and not c.runtime_minutes.maximum_inclusive,
        ),
        (
            {"imdb_rating": {"minimum": 7.5}},
            lambda c: c.imdb_rating.minimum == 7.5 and c.tmdb_rating.minimum is None,
        ),
        (
            {
                "genres": ["Thriller"],
                "actors": ["Leonardo DiCaprio"],
                "year": {"minimum": 2010, "minimum_inclusive": False},
                "runtime_minutes": {"maximum": 150, "maximum_inclusive": False},
                "imdb_rating": {"minimum": 7.5},
            },
            lambda c: (
                c.genres == ["Thriller"]
                and c.actors == ["Leonardo DiCaprio"]
                and c.year.minimum == 2010
                and c.runtime_minutes.maximum == 150
                and c.imdb_rating.minimum == 7.5
            ),
        ),
    ],
)
def test_structured_intent_supports_expected_constraints(required, assertions) -> None:
    intent = MovieSearchIntent.model_validate(
        {
            "is_movie_request": True,
            "required": required,
            "preferred": {},
            "sort_preference": "relevance",
            "quality_requested": False,
            "classification_reason": "movie request",
        }
    )
    assert assertions(intent.required)


def test_preference_is_kept_separate_from_required_constraint() -> None:
    intent = MovieSearchIntent.model_validate(
        {
            "is_movie_request": True,
            "required": {"genres": ["Thriller"]},
            "preferred": {"actors": ["Leonardo DiCaprio"]},
            "sort_preference": "relevance",
            "quality_requested": False,
            "classification_reason": "movie request",
        }
    )
    assert intent.required.actors == []
    assert intent.preferred.actors == ["Leonardo DiCaprio"]

