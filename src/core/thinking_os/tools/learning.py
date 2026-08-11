"""
Thinking OS — MCP learning tools.

Pattern mining and rule suggestion:
  - cos_learn_extract: discover patterns from task outcomes
  - cos_learn_suggest: return relevant patterns for current context
  - cos_learn_validate: confirm/deny a pattern's usefulness

Facade — the implementation lives in the `_learning_*` siblings; this module is
the stable import surface for hooks, the MCP server, the Hub and the CLI.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("thinking_os.learning")

# Dual import identity (flat `tools.learning` vs package `thinking_os.tools.learning`)
# — try the package form, fall back to the bare one.
try:  # package import
    from ._learning_extract import (
        MIN_DATA_THRESHOLD,
        learn_extract,
    )
    from ._learning_generalize import (
        _collapse_duplicate_patterns,
        _consolidate_semantic_duplicates,
        _format_generalize_draft,
        generalize_lessons,
    )
    from ._learning_mining import (
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _mine_friction_lessons,
        _mint_friction_lesson,
        _normalize_full,
    )
    from ._learning_mining_logs import (
        _commit_subject_key,
        _mine_commit_lessons,
        _mine_hook_block_lessons,
    )
    from ._learning_narrative import (
        _file_back_narrative_safe,
        _is_low_quality_insight,
        learn_narrative,
    )
    from ._learning_store import (
        _adopt_legacy_template,
        _derive_project_root,
        _distill_fingerprint_safe,
        _distill_safe,
        _embed_pattern_safe,
        _pattern_identity,
        _upsert_pattern,
        pattern_tier,
    )
    from ._learning_suggest import learn_suggest
    from ._learning_validate import (
        _THROTTLE_WINDOW_SECONDS,
        _has_recent_validation,
        _load_surfaced_suggestions,
        _log_validation,
        _read_session_id_for_validate,
        boost_success,
        learn_validate,
        penalize_failure,
        validate_surfaced_lessons,
    )
except ImportError:  # flat import
    from _learning_extract import (  # type: ignore[no-redef,import-not-found]
        MIN_DATA_THRESHOLD,
        learn_extract,
    )
    from _learning_generalize import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _collapse_duplicate_patterns,
        _consolidate_semantic_duplicates,
        _format_generalize_draft,
        generalize_lessons,
    )
    from _learning_mining import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _mine_friction_lessons,
        _mint_friction_lesson,
        _normalize_full,
    )
    from _learning_mining_logs import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _commit_subject_key,
        _mine_commit_lessons,
        _mine_hook_block_lessons,
    )
    from _learning_narrative import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _file_back_narrative_safe,
        _is_low_quality_insight,
        learn_narrative,
    )
    from _learning_store import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _adopt_legacy_template,
        _derive_project_root,
        _distill_fingerprint_safe,
        _distill_safe,
        _embed_pattern_safe,
        _pattern_identity,
        _upsert_pattern,
        pattern_tier,
    )
    from _learning_suggest import learn_suggest  # type: ignore[no-redef,import-not-found]
    from _learning_validate import (  # type: ignore[no-redef,import-not-found]  # noqa: F401
        _THROTTLE_WINDOW_SECONDS,
        _has_recent_validation,
        _load_surfaced_suggestions,
        _log_validation,
        _read_session_id_for_validate,
        boost_success,
        learn_validate,
        penalize_failure,
        validate_surfaced_lessons,
    )

__all__ = [
    "MIN_DATA_THRESHOLD",
    "boost_success",
    "generalize_lessons",
    "learn_extract",
    "learn_narrative",
    "learn_suggest",
    "learn_validate",
    "logger",
    "pattern_tier",
    "penalize_failure",
    "validate_surfaced_lessons",
]
