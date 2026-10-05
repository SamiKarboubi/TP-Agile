import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from psycopg import OperationalError

from app.api.routes import build_router
from app.api.accounts import build_account_router
from app.core.config import Settings, get_settings
from app.services.claude_service import ClaudeService
from app.services.errors import ApplicationServiceError
from app.services.mcp_service import MCPService
from app.services.movie_service import MovieRecommendationService
from app.services.account_store import AccountStore
from app.services.auth_service import AuthService
from app.services.postgres_account_store import PostgresAccountStore
from app.services.genre_catalog import GenreCatalog


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    analyzer: Any | None = None,
    recommender: Any | None = None,
    account_store: AccountStore | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    mcp_service: MCPService | None = None
    store = account_store if account_store is not None else PostgresAccountStore(app_settings)
    auth = AuthService(app_settings, store)

    if analyzer is None or recommender is None:
        mcp_service = MCPService(app_settings)
        genres = GenreCatalog(mcp_service)
        if analyzer is None:
            analyzer = ClaudeService(app_settings, genres)
        if recommender is None:
            recommender = MovieRecommendationService(app_settings, mcp_service, genres)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            await asyncio.to_thread(store.initialize)
        except OperationalError:
            raise RuntimeError("PostgreSQL est inaccessible. Vérifiez DB_HOST, DB_PORT, DB_NAME, DB_USER et DB_PASSWORD.") from None
        try:
            yield
        finally:
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
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-MovieMatch-Request", "X-MovieMatch-User"],
    )
    application.include_router(build_router(app_settings, analyzer, recommender, auth))
    application.include_router(build_account_router(app_settings, auth))

    @application.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        await asyncio.to_thread(store.check_health)
        return {"status": "ok"}

    @application.exception_handler(OperationalError)
    async def database_error_handler(_: Request, exc: OperationalError) -> JSONResponse:
        logger.warning("Database unavailable: %s", exc.__class__.__name__)
        return JSONResponse(status_code=503, content={"detail": "La base de données est temporairement indisponible."})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo passwords or other submitted values in validation responses.
        details = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                   for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

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
