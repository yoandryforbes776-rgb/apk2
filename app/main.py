"""Punto de entrada: `uvicorn app.main:app --host 0.0.0.0 --port 8080`."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import router as api_router
from .pool import KeyPool
from .registry import Registry, load_registry
from .router import RouterEngine, RouterError
from .settings import Settings
from .upstream import Upstream


def create_app(
    settings: Settings | None = None,
    registry: Registry | None = None,
    upstream: Upstream | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )

    registry = registry or load_registry(settings)
    pool = KeyPool(registry.providers, settings.state_path, settings.persist_keys)
    upstream = upstream or Upstream(settings)
    engine = RouterEngine(registry, pool, upstream, settings)

    if registry.load_error:
        logging.getLogger("router").error("Registro con problemas: %s", registry.load_error)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.getLogger("router").info(
            "Free AI Router %s | %s proveedores (%s con claves)",
            settings.version,
            len(registry.providers),
            len(registry.routable()),
        )
        try:
            yield
        finally:
            await upstream.aclose()

    app = FastAPI(
        title="Free AI Router",
        version=settings.version,
        description=(
            "Gateway compatible con la API de OpenAI que reparte peticiones entre "
            "proveedores de IA gratuitos y rota claves cuando se agota el límite."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.state.settings = settings
    app.state.registry = registry
    app.state.pool = pool
    app.state.upstream = upstream
    app.state.engine = engine
    app.state.started_at = time.time()

    if settings.allow_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=[
                "x-router-provider",
                "x-router-model",
                "x-router-key",
                "x-router-attempts",
                "x-router-latency-ms",
                "retry-after",
            ],
        )

    app.include_router(api_router)

    static_dir = settings.static_dir
    if static_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.exception_handler(RouterError)
    async def router_error_handler(_request: Request, exc: RouterError) -> JSONResponse:
        payload = {
            "error": {
                "message": exc.message,
                "type": exc.code,
                "code": exc.code,
                "router": {
                    "attempts": [a.to_dict() for a in exc.trace],
                    "retry_after": exc.retry_after,
                },
            }
        }
        headers = {"retry-after": str(int(exc.retry_after))} if exc.retry_after else None
        return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail)
        else:
            message = str(detail)
        kind = "invalid_request_error" if 400 <= exc.status_code < 500 else "server_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"message": message, "type": kind, "code": exc.status_code}},
            headers=exc.headers,
        )

    return app


app = create_app()
