import asyncio
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import Client, StdioServerParameters

from app.core.config import Settings
from app.services.errors import MCPServiceError, ServiceConfigurationError


@dataclass
class _ToolCall:
    name: str
    arguments: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]


class MCPService:
    """Own one persistent stdio MCP process from a dedicated asyncio task."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: asyncio.Queue[_ToolCall | None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.tmdb_api_token:
            raise ServiceConfigurationError("TMDB_API_TOKEN n’est pas configuré.")

        await self._ensure_worker()
        if self._queue is None:
            raise MCPServiceError("Le serveur TMDB MCP n’a pas pu démarrer.")

        future = asyncio.get_running_loop().create_future()
        await self._queue.put(_ToolCall(name=name, arguments=arguments, future=future))
        return await future

    async def _ensure_worker(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        async with self._start_lock:
            if self._worker is not None and not self._worker.done():
                return
            self._queue = asyncio.Queue()
            self._worker = asyncio.create_task(self._run_worker(self._queue))

    async def _run_worker(self, queue: asyncio.Queue[_ToolCall | None]) -> None:
        stack: AsyncExitStack | None = None
        client: Client | None = None
        try:
            while True:
                call = await queue.get()
                if call is None:
                    break
                try:
                    if client is None:
                        stack, client = await self._open_client()
                    result = await asyncio.wait_for(
                        client.call_tool(call.name, call.arguments),
                        timeout=self._settings.mcp_call_timeout_seconds,
                    )
                    payload = _structured_payload(call.name, result)
                except Exception as exc:
                    if stack is not None:
                        await stack.aclose()
                    stack, client = None, None
                    error = (
                        exc
                        if isinstance(exc, MCPServiceError)
                        else MCPServiceError(f"Le tool MCP {call.name} a échoué.")
                    )
                    if not call.future.done():
                        call.future.set_exception(error)
                else:
                    if not call.future.done():
                        call.future.set_result(payload)
        finally:
            if stack is not None:
                await stack.aclose()
            while not queue.empty():
                pending = queue.get_nowait()
                if pending is not None and not pending.future.done():
                    pending.future.set_exception(
                        MCPServiceError("Le serveur TMDB MCP a été arrêté.")
                    )

    async def _open_client(self) -> tuple[AsyncExitStack, Client]:
        stack = AsyncExitStack()
        try:
            parameters = StdioServerParameters(
                command=self._settings.tmdb_mcp_command,
                args=self._settings.mcp_args,
                env=self._settings.mcp_environment,
            )
            client = await stack.enter_async_context(Client(parameters))
        except Exception as exc:
            await stack.aclose()
            raise MCPServiceError("Impossible de démarrer le serveur TMDB MCP.") from exc
        return stack, client

    async def close(self) -> None:
        worker, queue = self._worker, self._queue
        self._worker = None
        self._queue = None
        if worker is not None and queue is not None:
            await queue.put(None)
            await worker


def _structured_payload(name: str, result: Any) -> dict[str, Any]:
    if getattr(result, "is_error", False):
        raise MCPServiceError(f"Le tool MCP {name} a renvoyé une erreur.")

    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise MCPServiceError(f"Le tool MCP {name} a renvoyé une réponse inexploitable.")
