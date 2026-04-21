"""core.web.server — FastAPI app factory + uvicorn launcher.

PURPOSE: Create and configure the unified web server that exposes graph-os,
         board-os, cognition, and search as /api/* REST routes.  Also mounts
         the SPA static files when core/web/ui/dist/ exists.
INPUT:   Environment variables: COS_WEB_PORT (default 4748),
         COS_WEB_HOST (default 127.0.0.1), COS_WEB_CORS_ALLOW_ALL.
OUTPUT:  FastAPI application instance (create_app()) or starts uvicorn
         (run_server()).
DEPENDENCIES: fastapi, uvicorn[standard], core.web.routes.*.
NOTES:  CORS is locked to http://localhost:5173 (Vite dev) + same-origin
        unless COS_WEB_CORS_ALLOW_ALL=1 (dev override).
        Static SPA is mounted last (catch-all) so API routes take priority.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

_CORE_DIR = Path(__file__).resolve().parent.parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

# Defaults
DEFAULT_PORT = int(os.environ.get("COS_WEB_PORT", "4748"))
DEFAULT_HOST = os.environ.get("COS_WEB_HOST", "127.0.0.1")

_SPA_DIST = Path(__file__).resolve().parent / "ui" / "dist"

_CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    f"http://localhost:{DEFAULT_PORT}",  # same-origin prod
    f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",  # bound interface
]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    PURPOSE: App factory — idempotent, importable by tests and production.
    INPUT:   none (reads env vars for port/CORS at call time).
    OUTPUT:  Configured FastAPI instance with all /api/* routes registered.
    DEPENDENCIES: fastapi, core.web.routes.*, core.web._deps.
    NOTES:  Registers routers lazily so missing extras (graph_os, board_os)
            don't prevent the server from starting; those routes return 503.
    """
    app = FastAPI(
        title="Coding OS Web API",
        description="Unified HTTP backbone for graph-os + board-os + cognition + search.",
        version="0.4.0",
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    cors_allow_all = os.environ.get("COS_WEB_CORS_ALLOW_ALL", "0").strip() == "1"
    if cors_allow_all:
        allow_origins = ["*"]
    else:
        allow_origins = _CORS_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=not cors_allow_all,  # can't send credentials with wildcard
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------
    from core.web.routes.board import router as board_router
    from core.web.routes.cognition import router as cognition_router
    from core.web.routes.graph import router as graph_router
    from core.web.routes.health import router as health_router
    from core.web.routes.metrics import router as metrics_router
    from core.web.routes.search import router as search_router
    from core.web.routes.stream import router as stream_router

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(graph_router)
    app.include_router(board_router)
    app.include_router(cognition_router)
    app.include_router(search_router)
    app.include_router(stream_router)

    # ------------------------------------------------------------------
    # Static SPA / fallback
    # ------------------------------------------------------------------
    if _SPA_DIST.exists() and _SPA_DIST.is_dir():
        # Mount the built SPA; index.html catches unmatched paths.
        app.mount("/", StaticFiles(directory=str(_SPA_DIST), html=True), name="spa")
    else:
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def spa_not_built():
            return HTMLResponse(
                content=(
                    "<html><body>"
                    "<h1>Coding OS Web Server</h1>"
                    "<p>API is running. SPA not built yet.</p>"
                    "<p>To build: <code>cd core/web/ui &amp;&amp; npm run build</code></p>"
                    "<p>API docs: <a href='/docs'>/docs</a></p>"
                    "</body></html>"
                ),
                status_code=200,
            )

    return app


def run_server(
    *,
    host: str | None = None,
    port: int | None = None,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Start the uvicorn server.

    PURPOSE: Production-ready launcher called by `cos web` CLI command.
    INPUT:   host, port, reload, log_level — all optional, fall back to env.
    OUTPUT:  none (blocks until server is stopped).
    DEPENDENCIES: uvicorn.
    NOTES:  Uses the app factory string "core.web.server:create_app" with
            factory=True so uvicorn can reload cleanly.  reload=True enables
            watchfiles for development.
    """
    import uvicorn

    _host = host or DEFAULT_HOST
    _port = port or DEFAULT_PORT

    uvicorn.run(
        "core.web.server:create_app",
        host=_host,
        port=_port,
        reload=reload,
        log_level=log_level,
        factory=True,
    )


if __name__ == "__main__":
    run_server()
