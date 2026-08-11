"""core.web.routes.config — read-only per-project Configuration surface.

Surfaces what is configured for the active project so a human can SEE it
without reading YAML/JSON: tech stacks (.coding-os.yaml::templates + the stack
registry), skills (the core skill registry), and MCP servers (.mcp.json).

Read-only this phase. Per-project enable/disable for skills/MCP/hooks is a
separate kernel-override epic (a Hub toggle must never edit the global
registry). Hooks already have /api/hooks/list, so they are not duplicated here.

Available stacks/skills are read from the installed package (CODING_OS_ROOT),
not the project tree, so the surface works identically in the meta-repo and in
a scaffolded consumer that has no src/templates of its own.
"""

from __future__ import annotations

from ._config_shared import router as router

# Import order IS the route order FastAPI resolves in: reads registered first,
# mutations second, exactly as the single pre-split module declared them.
from . import _config_read as _config_read  # isort: skip
from . import _config_mutate as _config_mutate  # isort: skip
