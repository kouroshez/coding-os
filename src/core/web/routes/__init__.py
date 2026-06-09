"""core.web.routes — route module registry."""

from .board import router as board_router
from .cognition import router as cognition_router
from .graph import router as graph_router
from .health import router as health_router
from .hooks import router as hooks_router
from .logs import router as logs_router
from .metrics import router as metrics_router
from .patterns import router as patterns_router
from .search import router as search_router
from .stream import router as stream_router

__all__ = [
    "board_router",
    "cognition_router",
    "graph_router",
    "health_router",
    "hooks_router",
    "logs_router",
    "metrics_router",
    "patterns_router",
    "search_router",
    "stream_router",
]
