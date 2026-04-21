"""core.web.routes — route module registry.

PURPOSE: Re-export every APIRouter so server.py can import them in one place.
INPUT:   none.
OUTPUT:  routers: graph_router, board_router, cognition_router, search_router,
         stream_router, health_router, metrics_router.
DEPENDENCIES: fastapi, sub-modules in this package.
NOTES:  Each router has its own prefix (/api/graph, /api/board, …).
"""

from .board import router as board_router
from .cognition import router as cognition_router
from .graph import router as graph_router
from .health import router as health_router
from .metrics import router as metrics_router
from .search import router as search_router
from .stream import router as stream_router

__all__ = [
    "graph_router",
    "board_router",
    "cognition_router",
    "search_router",
    "stream_router",
    "health_router",
    "metrics_router",
]
