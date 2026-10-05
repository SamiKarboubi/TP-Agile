import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.schemas.intents import MovieConstraints, MovieSearchIntent
from app.services.claude_service import ClaudeService
from app.services.errors import ClaudeServiceError, MCPServiceError
from app.services.genre_catalog import GenreCatalog


class GenreMCP:
    def __init__(self):
        self.calls = 0

    async def call_tool(self, name, arguments):
        assert name == 'get_movie_genres' and arguments == {}
        self.calls += 1
        await asyncio.sleep(0)
        return {'genres': [{'id': 27, 'name': 'Horreur'}, {'id': 878, 'name': 'Science-Fiction'},
                           {'id': 35, 'name': 'Comédie'}]}


@pytest.mark.asyncio
async def test_catalog_is_shared_and_cached_even_for_concurrent_requests():
    mcp = GenreMCP()
    catalog = GenreCatalog(mcp)
    results = await asyncio.gather(*(catalog.get() for _ in range(5)))
    assert mcp.calls == 1
    assert all(result is results[0] for result in results)


@pytest.mark.asyncio
async def test_invalid_catalog_is_not_cached_and_can_be_retried():
    mcp = SimpleNamespace(call_tool=AsyncMock(side_effect=[{'genres': []}, {'genres': [{'id': 27, 'name': 'Horreur'}]}]))
    catalog = GenreCatalog(mcp)
    with pytest.raises(MCPServiceError):
        await catalog.get()
    assert (await catalog.get())[0].name == 'Horreur'


@pytest.mark.asyncio
@pytest.mark.parametrize('genres', [[], ['Horreur'], ['Horreur', 'Science-Fiction', 'Horreur']])
async def test_claude_receives_actual_catalog_and_constrained_schema(genres):
    mcp = GenreMCP()
    service = ClaudeService(Settings(_env_file=None, anthropic_api_key='test-only'), GenreCatalog(mcp))

    async def parse(**kwargs):
        assert 'Available MCP movie genres: ["Horreur", "Science-Fiction", "Comédie"]' in kwargs['system']
        model = kwargs['output_format']
        enums = [definition['enum'] for definition in model.model_json_schema()['$defs'].values() if 'enum' in definition]
        assert ['Horreur', 'Science-Fiction', 'Comédie'] in enums
        return SimpleNamespace(parsed_output=model.model_validate({
            'is_movie_request': True, 'required': {'genres': genres, 'excluded_genres': ['Comédie']},
            'preferred': {'genres': ['Science-Fiction']}, 'quality_requested': False,
            'classification_reason': 'test',
        }))

    service._client.messages.parse = AsyncMock(side_effect=parse)
    for _ in range(2):
        result = await service.analyze('Un film qui fait peur')
        assert type(result) is MovieSearchIntent
        assert result.required.genres == list(dict.fromkeys(genres))
        assert result.required.excluded_genres == ['Comédie']
        assert result.preferred.genres == ['Science-Fiction']
    assert mcp.calls == 1


@pytest.mark.asyncio
async def test_invented_genres_are_rejected_instead_of_silently_dropping_a_filter():
    service = ClaudeService(Settings(_env_file=None, anthropic_api_key='test-only'), GenreCatalog(GenreMCP()))
    service._client.messages.parse = AsyncMock(return_value=SimpleNamespace(parsed_output=MovieSearchIntent(
        is_movie_request=True, required=MovieConstraints(genres=['Psychologique']),
        preferred=MovieConstraints(), quality_requested=False, classification_reason='test',
    )))
    with pytest.raises(ClaudeServiceError):
        await service.analyze('Un thriller psychologique')
