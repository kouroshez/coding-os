"""core.web.server — FastAPI app factory + uvicorn launcher."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

_CORE_DIR = Path(__file__).resolve().parent.parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

# Defaults
DEFAULT_PORT = int(os.environ.get("COS_WEB_PORT", "9188"))
DEFAULT_HOST = os.environ.get("COS_WEB_HOST", "127.0.0.1")

_SPA_DIST = Path(__file__).resolve().parent / "ui" / "dist"

_CORS_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    f"http://localhost:{DEFAULT_PORT}",  # same-origin prod
    f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",  # bound interface
]


TAGS_METADATA = [
    {
        "name": "board",
        "description": "Scrumban board state — tasks, columns, daily/wip/retro/pick.",
    },
    {
        "name": "cognition",
        "description": "Cognitive cycle artifacts — traces, dispatchers, costs, Claude SDK chats.",
    },
    {
        "name": "graph",
        "description": "graph_os knowledge graph — context, impact, export, rename-plan, communities.",
    },
    {
        "name": "health",
        "description": "Liveness probe — backend status + file_index_state freshness.",
    },
    {
        "name": "hooks",
        "description": "Hook registry + live event stream from .coding-os/.hooks.log.",
    },
    {"name": "hub", "description": "Multi-project Hub — registry, suggest-roots, GC."},
    {
        "name": "metrics",
        "description": "Prometheus text-format counters + summary quantiles (cos_web_*).",
    },
    {
        "name": "observability",
        "description": "Cross-source timeline — hooks + cognition + sessions.",
    },
    {"name": "presence", "description": "Who-is-active aggregate across agents (single-shot)."},
    {
        "name": "roles",
        "description": "11 semantic roles + active formula chain + per-formula outputs.",
    },
    {"name": "scheduled", "description": "Cron-style scheduled formula dispatches."},
    {
        "name": "search",
        "description": "Four-layer retrieval — memory, docs, tasks (semantic + keyword).",
    },
    {
        "name": "sessions",
        "description": "Per-project agent presence (active / present / idle / offline / ended).",
    },
    {"name": "settings", "description": "Hub configuration — read + patch."},
    {
        "name": "stream",
        "description": "Server-sent events: live tool/state changes + replayable history.",
    },
]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Route every stdlib logger.error and uncaught
    # route 500 into logging_os so the web process is no longer blind to its
    # own failures. Idempotent — install_bridge() removes a prior bridge
    # handler before adding. See docs/engineering/observability-eye.md §1.
    from logging_os import setup as _logging_os_setup

    _logging_os_setup(level="info")

    _host_for_servers = os.environ.get("COS_WEB_HOST", "127.0.0.1")
    _port_for_servers = int(os.environ.get("COS_WEB_PORT", "9188"))
    app = FastAPI(
        title="Coding OS Web API",
        description=(
            "Unified HTTP backbone for graph_os + board_os + cognition + search.\n\n"
            "All routes follow the MCP envelope contract — `{data, meta}` on 2xx, "
            "`{error: {category, message, retryable}}` on 4xx/5xx. "
            "See `docs/engineering/mcp-error-envelope.md`."
        ),
        version="0.4.0",
        openapi_tags=TAGS_METADATA,
        servers=[
            {"url": f"http://{_host_for_servers}:{_port_for_servers}", "description": "Local Hub"},
        ],
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

    # Gzip every response over 500 bytes — /api/graph/export payloads are
    # 200-300 KB JSON and compress to ~10-20% (5-10x faster transfer on
    # any network slower than localhost). minimum_size=500 skips tiny
    # health responses where the gzip header overhead is net negative.
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Per-request project scope — lets a single uvicorn serve every
    # registered coding-os project under /api/p/<slug>/...  (Hub mode).
    # Legacy launches without /p/<slug>/ keep using the cwd/env fallback.
    from web._project_context import ProjectScopeMiddleware

    app.add_middleware(ProjectScopeMiddleware)

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------
    from web.routes.audits import router as audits_router
    from web.routes.board import router as board_router
    from web.routes.cognition import router as cognition_router
    from web.routes.config import router as config_router
    from web.routes.graph import router as graph_router
    from web.routes.health import router as health_router
    from web.routes.hooks import router as hooks_router
    from web.routes.hub import router as hub_router
    from web.routes.logs import router as logs_router
    from web.routes.metrics import router as metrics_router
    from web.routes.observability import router as observability_router
    from web.routes.presence import router as presence_router
    from web.routes.roles import router as roles_router
    from web.routes.scheduled import router as scheduled_router
    from web.routes.patterns import router as patterns_router
    from web.routes.search import router as search_router
    from web.routes.sessions import router as sessions_router
    from web.routes.settings import router as settings_router
    from web.routes.stream import router as stream_router

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(graph_router)
    app.include_router(board_router)
    app.include_router(cognition_router)
    app.include_router(config_router)
    app.include_router(hooks_router)
    app.include_router(logs_router)
    app.include_router(observability_router)
    app.include_router(presence_router)
    app.include_router(roles_router)
    app.include_router(patterns_router)
    app.include_router(search_router)
    app.include_router(sessions_router)
    app.include_router(settings_router)
    app.include_router(stream_router)
    app.include_router(hub_router)
    app.include_router(scheduled_router)
    app.include_router(audits_router)

    # ------------------------------------------------------------------
    # Static SPA / fallback
    # ------------------------------------------------------------------
    # NOTES ON ROUTING
    # All /api/* routes are registered above. Anything else is either
    # a built SPA asset (dist/assets/**, dist/index.html, root-level
    # files like dist/cos-board-tokens.css) or a SPA client-side route
    # (/board, /graph, /cognition, /search, ...).  StaticFiles with
    # html=True only handles the top-level index; deep links like
    # /board produce 404s.  To support SPA deep links we mount /assets
    # separately and add a catch-all that returns index.html for any
    # unmatched path (while letting unknown /api/* paths 404 cleanly).
    if _SPA_DIST.exists() and _SPA_DIST.is_dir():
        assets_dir = _SPA_DIST / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="spa-assets",
            )

        @app.get("/{spa_path:path}", include_in_schema=False)
        async def spa_fallback(spa_path: str):
            """Serve root-level static files if present; otherwise return
            the SPA index.html so React Router can take over."""
            if spa_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            # Root-level files (favicon, cos-board-tokens.css, ...).
            if spa_path:
                candidate = (_SPA_DIST / spa_path).resolve()
                try:
                    candidate.relative_to(_SPA_DIST.resolve())
                except ValueError:
                    raise HTTPException(status_code=404, detail="Not Found")
                if candidate.is_file():
                    return FileResponse(candidate)
            # Default — hand control to the React SPA.
            return FileResponse(_SPA_DIST / "index.html")
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
    """Start the uvicorn server."""
    import uvicorn

    _host = host or DEFAULT_HOST
    _port = port or DEFAULT_PORT

    uvicorn.run(
        "web.server:create_app",
        host=_host,
        port=_port,
        reload=reload,
        log_level=log_level,
        factory=True,
    )


if __name__ == "__main__":
    run_server()
