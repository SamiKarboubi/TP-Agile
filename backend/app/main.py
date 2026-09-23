import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import build_router
from app.core.config import Settings, get_settings
from app.services.claude_service import ClaudeService
from app.services.errors import ApplicationServiceError
from app.services.mcp_service import MCPService
from app.services.movie_service import MovieRecommendationService


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    analyzer: Any | None = None,
    recommender: Any | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    mcp_service: MCPService | None = None

    if analyzer is None:
        analyzer = ClaudeService(app_settings)
    if recommender is None:
        mcp_service = MCPService(app_settings)
        recommender = MovieRecommendationService(app_settings, mcp_service)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if mcp_service is not None:
            await mcp_service.close()

    application = FastAPI(
        title="Movie Recommendation API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(build_router(app_settings, analyzer, recommender))

    @application.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(ApplicationServiceError)
    async def service_error_handler(
        _: Request, exc: ApplicationServiceError
    ) -> JSONResponse:
        logger.warning("Service error: %s", exc.__class__.__name__)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.public_message},
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected request failure", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Une erreur interne est survenue."},
        )

    return application


app = create_app()
