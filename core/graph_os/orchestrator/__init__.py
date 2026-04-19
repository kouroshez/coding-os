"""graph-os orchestrator — role registry + dispatcher + worker pool (I.9).

The orchestrator runs long-lived tasks outside the MCP server's critical
path: embedding migration, LSP warm-start, file indexing. Each task is
encoded as a `Role`; the dispatcher owns execution; the worker pool
keeps a bounded fleet of subprocess-free workers (Python threads in
I.9; the real thinking-os agent-run model lands in I.9b).

The plan (§13) names this module `core/thinking-os/orchestrator/`. We
co-locate it inside graph_os because Phase I ships the infrastructure
there first; when thinking-os needs orchestrator roles of its own,
it can import from `graph_os.orchestrator`.
"""

from .registry import Role, RoleContext, RoleResult, RoleRegistry, default_registry
from .dispatcher import Dispatcher
from .worker_pool import WorkerPool
from .progress import ProgressReporter

__all__ = [
    "Role",
    "RoleContext",
    "RoleResult",
    "RoleRegistry",
    "default_registry",
    "Dispatcher",
    "WorkerPool",
    "ProgressReporter",
]
