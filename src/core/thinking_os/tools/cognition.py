"""Coding OS — Formula-agent supervisor MCP tools.

Facade over the cognition surface: `register_all` is the single entry the MCP
server calls, and every name a sibling or test reached for through this module
is re-exported below so the split is invisible to callers.
"""

from __future__ import annotations

import logging

from ._cognition_audit import (
    CANONICAL_REMEDIES as CANONICAL_REMEDIES,
    register_cos_ambiguity_check as register_cos_ambiguity_check,
    register_cos_backtrack_log as register_cos_backtrack_log,
    register_cos_discovery as register_cos_discovery,
    register_cos_traceability as register_cos_traceability,
)
from ._cognition_classify import (
    classify_prompt_heuristic as classify_prompt_heuristic,
    register_cos_classify_prompt as register_cos_classify_prompt,
)
from ._cognition_dispatch import (
    _build_dispatch_request as _build_dispatch_request,
    _emit_dispatch_metrics_safe as _emit_dispatch_metrics_safe,
    _empirical_model as _empirical_model,
    _persist_dispatch_output as _persist_dispatch_output,
    _preset_role_hint as _preset_role_hint,
    _resolve_dispatch_model as _resolve_dispatch_model,
    register_cos_dispatch_formula as register_cos_dispatch_formula,
    register_cos_dispatch_formula_run as register_cos_dispatch_formula_run,
    register_cos_dispatch_parallel_run as register_cos_dispatch_parallel_run,
)
from ._cognition_routing import (
    register_cos_analyze_task as register_cos_analyze_task,
    register_cos_compose_chain as register_cos_compose_chain,
    register_cos_role_info as register_cos_role_info,
    register_cos_situation_detect as register_cos_situation_detect,
)
from ._cognition_shared import (
    _all_bundle_fields as _all_bundle_fields,
    _bundle_path as _bundle_path,
    _cog as _cog,
    _load_bundle as _load_bundle,
    _now_iso as _now_iso,
    _resolve_agent_dir as _resolve_agent_dir,
    _resolve_role_persistence as _resolve_role_persistence,
    _save_bundle as _save_bundle,
    _schemas as _schemas,
)
from ._cognition_supervise import (
    register_cos_supervise as register_cos_supervise,
    register_cos_supervise_record_output as register_cos_supervise_record_output,
    register_cos_supervision_config as register_cos_supervision_config,
    register_cos_takeover as register_cos_takeover,
)

logger = logging.getLogger("coding_os.tools.cognition")


def register_all(mcp, db_path: str) -> None:
    """Register all cognition tools with the MCP server."""
    register_cos_supervise(mcp, db_path)
    register_cos_supervise_record_output(mcp, db_path)
    register_cos_dispatch_formula(mcp, db_path)
    register_cos_ambiguity_check(mcp, db_path)
    register_cos_traceability(mcp, db_path)
    register_cos_backtrack_log(mcp, db_path)
    register_cos_discovery(mcp, db_path)
    register_cos_situation_detect(mcp, db_path)
    register_cos_takeover(mcp, db_path)
    # Additions
    register_cos_analyze_task(mcp, db_path)
    register_cos_compose_chain(mcp, db_path)
    register_cos_role_info(mcp, db_path)
    # real dispatch (opt-in, costly)
    register_cos_dispatch_formula_run(mcp, db_path)
    register_cos_dispatch_parallel_run(mcp, db_path)
    # auto-Classify (eliminates manual gate recording)
    register_cos_classify_prompt(mcp, db_path)
    register_cos_supervision_config(mcp, db_path)
