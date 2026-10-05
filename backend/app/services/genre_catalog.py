import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.errors import MCPServiceError


class GenreClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MovieGenre:
    id: int
    name: str


class GenreCatalog:
    """One validated MCP catalog shared by classification and filtering."""

    def __init__(self, mcp: GenreClient) -> None:
        self._mcp = mcp
        self._genres: tuple[MovieGenre, ...] | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> tuple[MovieGenre, ...]:
        async with self._lock:
            if self._genres is None:
                payload = await self._mcp.call_tool("get_movie_genres", {})
                items = payload.get("genres")
                if not isinstance(items, list) or not items or any(
                    not isinstance(item, dict) or type(item.get("id")) is not int
                    or item["id"] <= 0 or not isinstance(item.get("name"), str)
                    or not item["name"].strip() for item in items
                ):
                    raise MCPServiceError("La liste des genres de films est indisponible. Réessayez.")
                self._genres = tuple(MovieGenre(item["id"], item["name"].strip()) for item in items)
            return self._genres
