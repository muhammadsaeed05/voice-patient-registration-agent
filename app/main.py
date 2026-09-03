from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import create_db_and_tables
from .routers import health_router, patients_router, tools_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("voice_patient_agent.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables and seed baseline records if empty."""
    create_db_and_tables()
    yield


def create_app() -> FastAPI:
    """FastAPI application factory with middleware, envelope error handlers, and routers."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Voice AI Patient Registration API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standardized response envelope error handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_messages = []
        for error in exc.errors():
            loc = " -> ".join(str(loc_part) for loc_part in error.get("loc", []))
            msg = error.get("msg", "Invalid value")
            error_messages.append(f"{loc}: {msg}")
        error_summary = "; ".join(error_messages)
        logger.warning(f"Validation error on {request.method} {request.url.path}: {error_summary}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"data": None, "error": f"Validation error: {error_summary}"},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning(f"HTTP exception {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"data": None, "error": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"data": None, "error": f"Internal server error: {str(exc)}"},
        )

    app.include_router(health_router)
    app.include_router(patients_router)
    app.include_router(tools_router)

    return app


app = create_app()


def start():
    """CLI entrypoint to start the Uvicorn ASGI server."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    start()
