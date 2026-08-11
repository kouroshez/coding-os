"""graph_os — SQLite fallback backend.

DEPENDS:  sqlite3 stdlib; core/thinking_os/database.py for init_db when
          path-based; core/graph_os/types.py for the value types.

Facade — the implementation is split across `_sqlite_connection` (lifecycle),
`_sqlite_write`, `_sqlite_links` and `_sqlite_read`.
"""

from __future__ import annotations

import logging

from ._sqlite_connection import _import_db_module as _import_db_module
from ._sqlite_links import _SqliteLinkMixin
from ._sqlite_read import _SqliteReadMixin
from ._sqlite_write import _SqliteWriteMixin

logger = logging.getLogger("graph_os.backends.sqlite")


class SqliteBackend(_SqliteWriteMixin, _SqliteLinkMixin, _SqliteReadMixin):
    """SQLite-backed graph store (thinking_os DB, migration v12).

    DEPENDS:  migration v12 (graph_nodes, graph_edges_v12,
              graph_evidence_v12 tables + optional FTS5 virtual
              table).
    """


__all__ = ["SqliteBackend"]
