from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.constants import OUT_OF_SCOPE_MESSAGE
from app.main import create_app
from app.schemas.intents import MovieConstraints, MovieSearchIntent
from app.schemas.recommendations import MovieResult, RecommendationResponse


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, message: str) -> MovieSearchIntent:
        self.calls.append(message)
        return MovieSearchIntent(
            is_movie_request="kubernetes" not in message.casefold(),
            required=MovieConstraints(genres=["Thriller"] if "thriller" in message.casefold() else []),
            preferred=MovieConstraints(),
            classification_reason="Test classification",
            quality_requested=False,
        )


class FakeRecommender:
    def __init__(self) -> None:
        self.calls = 0
        self.lookup_ids: list[int] = []
        self.favorite_ids: list[int] = []

    async def lookup_movies(self, ids: list[int]) -> list[MovieResult]:
        self.lookup_ids = ids
        return [MovieResult(id=movie_id, title=f"Film {movie_id}") for movie_id in ids]

    async def recommend(
        self, _: MovieSearchIntent, favorite_ids: list[int] | None = None
    ) -> RecommendationResponse:
        self.calls += 1
        self.favorite_ids = favorite_ids or []
        return RecommendationResponse(message="Résultat simulé", movies=[])


def make_client(max_length: int = 200) -> tuple[TestClient, FakeAnalyzer, FakeRecommender]:
    analyzer = FakeAnalyzer()
    recommender = FakeRecommender()
    settings = Settings(max_user_message_length=max_length)
    app = create_app(settings=settings, analyzer=analyzer, recommender=recommender)
    return TestClient(app), analyzer, recommender


def test_health_check() -> None:
    client, _, _ = make_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_message_is_rejected() -> None:
    client, analyzer, _ = make_client()
    response = client.post("/api/recommendations", json={"message": "   "})
    assert response.status_code == 422
    assert analyzer.calls == []


def test_too_long_message_is_rejected() -> None:
    client, analyzer, _ = make_client(max_length=200)
    response = client.post("/api/recommendations", json={"message": "a" * 201})
    assert response.status_code == 422
    assert analyzer.calls == []


def test_movie_request_reaches_recommender() -> None:
    client, _, recommender = make_client()
    response = client.post("/api/recommendations", json={"message": "Je veux un thriller"})
    assert response.status_code == 200
    assert recommender.calls == 1


def test_favorite_ids_are_passed_to_recommender_without_duplicates() -> None:
    client, _, recommender = make_client()

    response = client.post(
        "/api/recommendations", json={"message": "Un thriller", "favorite_ids": [7, 3, 7]}
    )

    assert response.status_code == 200
    assert recommender.favorite_ids == [7, 3]


def test_invalid_favorite_ids_are_rejected() -> None:
    client, _, recommender = make_client()

    assert client.post(
        "/api/recommendations", json={"message": "Un film", "favorite_ids": [0]}
    ).status_code == 422
    assert client.post(
        "/api/recommendations", json={"message": "Un film", "favorite_ids": list(range(1, 22))}
    ).status_code == 422
    assert recommender.calls == 0


def test_out_of_scope_request_uses_fixed_response_without_movie_calls() -> None:
    client, _, recommender = make_client()
    response = client.post(
        "/api/recommendations", json={"message": "Explique-moi Kubernetes"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": OUT_OF_SCOPE_MESSAGE, "movies": []}
    assert recommender.calls == 0


def test_movie_lookup_returns_details_without_analyzing_message() -> None:
    client, analyzer, recommender = make_client()

    response = client.post("/api/movies/lookup", json={"ids": [7, 3, 7]})

    assert response.status_code == 200
    assert [movie["id"] for movie in response.json()["movies"]] == [7, 3]
    assert recommender.lookup_ids == [7, 3]
    assert analyzer.calls == []


def test_movie_lookup_rejects_invalid_or_excessive_ids() -> None:
    client, _, recommender = make_client()

    assert client.post("/api/movies/lookup", json={"ids": [0]}).status_code == 422
    assert client.post("/api/movies/lookup", json={"ids": list(range(1, 22))}).status_code == 422
    assert recommender.lookup_ids == []
