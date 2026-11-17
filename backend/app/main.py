"""FastAPI application factory (docs/ARCHITECTURE.md)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import request_id_var
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import AppError, RateLimited, error_body
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    from app.graphs import register_all
    from app.services.seed import seed_taxonomy

    if settings.app_env == "local" and not settings.database_url:  # embedded dev DB: migrate automatically
        import asyncio
        import subprocess
        import sys

        from app.core.config import BACKEND_DIR

        await asyncio.to_thread(subprocess.run, [sys.executable, str(BACKEND_DIR / "scripts" / "migrate.py")], cwd=BACKEND_DIR,
                                check=True)
    register_all()
    await seed_taxonomy()
    runner = None
    if settings.task_runner_enabled:
        from app.tasks.runner import TaskRunner

        runner = TaskRunner()
        await runner.start()
    log.info("startup", env=settings.app_env, llm=settings.llm_model_label, embeddings=settings.embedding_model_label,
             auth=settings.auth_mode, storage=settings.storage_backend, runner=bool(runner))
    yield
    if runner:
        await runner.stop()
    from app.graphs.runtime import close_checkpointer

    await close_checkpointer()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CareerPilot AI API", version="0.1.0", lifespan=lifespan,
        openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None,
        description="Evidence-backed job intelligence. Scores are prioritisation heuristics, not shortlist probabilities.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
                       expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
        request_id_var.set(rid)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
        return JSONResponse(error_body(exc.code, exc.message, exc.details, request_id_var.get()), status_code=exc.status_code,
                            headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
        return JSONResponse(error_body("validation_error", "Some fields are invalid.", {"fields": fields}, request_id_var.get()),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}.get(exc.status_code, "bad_request")
        return JSONResponse(error_body(code, str(exc.detail), None, request_id_var.get()), status_code=exc.status_code)

    from sqlalchemy.exc import IntegrityError

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(error_body("conflict", "This change conflicts with related records.", None, request_id_var.get()),
                            status_code=409)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", path=request.url.path)
        return JSONResponse(error_body("internal_error", "Something went wrong.", None, request_id_var.get()), status_code=500)

    from app.api.v1.router import api_router

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
