"""AI Gateway main application entry point."""

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.config import settings
from app.core.exceptions import AIGatewayError
from app.storage import close_db, init_db, RedisManager

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(structlog.stdlib, settings.log_level, structlog.stdlib.INFO)
    ),
    logger_factory=structlog.asyncio.AsyncLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info(
        "ai_gateway_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize database
    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        raise

    # Initialize Redis
    try:
        redis = await RedisManager.get_client()
        await redis.ping()
        logger.info("redis_initialized")
    except Exception as e:
        logger.warning("redis_init_failed", error=str(e))

    yield

    # Shutdown
    logger.info("ai_gateway_shutting_down")
    await close_db()
    await RedisManager.close()
    logger.info("ai_gateway_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="""
AI Gateway - A production-grade gateway for LLM providers.

## Features
- Multi-provider support (OpenAI, Anthropic, Azure, Bedrock, etc.)
- OpenAI-compatible API endpoints
- Rate limiting at multiple levels (key, tenant, channel)
- Flexible routing strategies (weighted, cost-optimized, latency-optimized)
- Token-level billing and quota management
- MCP protocol support
- Comprehensive observability

## Authentication
All API requests require an API key. Use the `Authorization: Bearer <key>` header
or `X-API-Key` header.
        """,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Include API routes
    app.include_router(api_router)

    # Exception handlers
    @app.exception_handler(AIGatewayError)
    async def ai_gateway_error_handler(
        request: Request, exc: AIGatewayError
    ) -> JSONResponse:
        """Handle AI Gateway specific errors."""
        logger.warning(
            "ai_gateway_error",
            error_code=exc.code,
            message=exc.message,
            path=request.url.path,
        )

        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        # Map error codes to HTTP status codes
        if "AUTHENTICATION" in exc.code or exc.code == "AUTHENTICATION_ERROR":
            status_code = status.HTTP_401_UNAUTHORIZED
        elif "AUTHORIZATION" in exc.code or exc.code == "AUTHORIZATION_ERROR":
            status_code = status.HTTP_403_FORBIDDEN
        elif "NOT_FOUND" in exc.code:
            status_code = status.HTTP_404_NOT_FOUND
        elif "QUOTA" in exc.code:
            status_code = status.HTTP_402_PAYMENT_REQUIRED
        elif "RATE_LIMIT" in exc.code:
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif "MODEL" in exc.code:
            status_code = status.HTTP_400_BAD_REQUEST
        elif "CHANNEL" in exc.code and "UNAVAILABLE" in exc.code:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif "VALIDATION" in exc.code:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors."""
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred"
                    if not settings.debug
                    else str(exc),
                }
            },
        )

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
    )
