"""core.web — Unified HTTP backbone for graph_os (S4).

PURPOSE: FastAPI application package exposing graph + board + cognition +
         search as /api/* REST routes, SSE for live updates, and static SPA
         hosting when core/web/ui/dist/ exists.
INPUT:   none (import-time side-effect-free; call create_app() to get the app).
OUTPUT:  FastAPI application instance via create_app().
DEPENDENCIES: fastapi, uvicorn[standard], sse-starlette, core.graph_os,
              core.board_os, core.thinking_os.
NOTES:  Port defaults to 9188 (env COS_WEB_PORT). CORS is locked to
        http://localhost:5173 (Vite dev) + same-origin unless
        COS_WEB_CORS_ALLOW_ALL=1.
"""

from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
