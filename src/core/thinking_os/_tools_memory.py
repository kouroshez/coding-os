"""Metric, memory, and learning cos_* tools registered on the shared server.

The three groups live in leaves — metrics/logs, memory recall, and the learning
loop. Importing this module registers all three on the shared `mcp` instance and
re-exports their tool functions, so `server.py`'s import list is unchanged.
"""

from __future__ import annotations

from _tools_learning import (
    cos_learn_extract as cos_learn_extract,
    cos_learn_narrative as cos_learn_narrative,
    cos_learn_suggest as cos_learn_suggest,
    cos_learn_validate as cos_learn_validate,
)
from _tools_metrics import (
    cos_log_query as cos_log_query,
    cos_metric_query as cos_metric_query,
    cos_metric_record as cos_metric_record,
    cos_metric_trend as cos_metric_trend,
)
from _tools_recall import (
    cos_observation_record as cos_observation_record,
    thinking_os_details as thinking_os_details,
    thinking_os_promote_tool as thinking_os_promote_tool,
    thinking_os_search as thinking_os_search,
    thinking_os_timeline as thinking_os_timeline,
)
