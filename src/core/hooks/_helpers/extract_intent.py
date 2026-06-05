"""Parse a user prompt for exhaustive-scope intent (FA + EN).

Mirror of docs/engineering/intent-vocabulary.md — when that doc changes,
the constants below MUST be updated. tests/test_intent_vocabulary_sync.py
enforces the mirror.

Triggered by src/core/hooks/detect-exhaustive-intent.sh on UserPromptSubmit.
Writes the parsed result to $COS_AGENT_DIR/.intent.json so downstream
consumers (completion guardian, count-grounding hook, subagent-delegation
hook, audit-artifact enforcement) read a single canonical record per
prompt instead of re-parsing.

Decision rule: a prompt has exhaustive intent IFF an exhaustive verb and
a scope verb co-occur within a 20-token sliding window. The predicates
inherited from all matched exhaustive verbs are UNIONED in the result.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WINDOW_TOKENS = 20

EXHAUSTIVE_VERBS_FA: dict[str, list[str]] = {
    "همه": ["coverage_100", "iterate_until_zero_residual"],
    "همگی": ["coverage_100"],
    "تک به تک": ["per_item_evidence"],
    "تا اخر": ["iterate_until_zero_residual"],
    "تا آخر": ["iterate_until_zero_residual"],
    "تا دونه آخر": ["iterate_until_zero_residual", "strict_zero_residual"],
    "تا دانه آخر": ["iterate_until_zero_residual", "strict_zero_residual"],
    "هر چی": ["exhaustive_grep"],
    "هر چیزی": ["exhaustive_grep"],
    "همه جا": ["exhaustive_grep"],
    "کامل": ["all_categories_evidence"],
    "کاملا": ["all_categories_evidence", "strict_zero_residual"],
    "کاملاً": ["all_categories_evidence", "strict_zero_residual"],
    "صد در صد": ["strict_zero_residual"],
    "هیچی نپره": ["strict_zero_residual"],
    "هیچی جا نمونه": ["strict_zero_residual"],
    "بدون استثنا": ["strict_zero_residual"],
    "بدون استثناء": ["strict_zero_residual"],
    "تمام": ["coverage_100"],
    "تمامی": ["coverage_100"],
}

EXHAUSTIVE_VERBS_EN: dict[str, list[str]] = {
    "all": ["coverage_100", "iterate_until_zero_residual"],
    "every": ["exhaustive_grep", "per_item_evidence"],
    "everything": ["exhaustive_grep"],
    "everywhere": ["exhaustive_grep"],
    "every single": ["per_item_evidence", "strict_zero_residual"],
    "completely": ["all_categories_evidence", "strict_zero_residual"],
    "comprehensive": ["coverage_100", "all_categories_evidence"],
    "comprehensively": ["coverage_100", "all_categories_evidence"],
    "exhaustive": ["coverage_100", "iterate_until_zero_residual"],
    "exhaustively": ["coverage_100", "iterate_until_zero_residual"],
    "thorough": ["all_categories_evidence"],
    "thoroughly": ["all_categories_evidence"],
    "deep audit": ["all_categories_evidence", "per_item_evidence"],
    "deep review": ["all_categories_evidence", "per_item_evidence"],
    "until done": ["iterate_until_zero_residual"],
    "no exceptions": ["strict_zero_residual"],
    "none missed": ["strict_zero_residual"],
    "100%": ["strict_zero_residual"],
    "down to the last one": ["iterate_until_zero_residual", "strict_zero_residual"],
    "each and every": ["per_item_evidence"],
    "top to bottom": ["coverage_100", "all_categories_evidence"],
}

SCOPE_VERBS_EN: set[str] = {
    "find",
    "fix",
    "update",
    "rename",
    "migrate",
    "audit",
    "verify",
    "check",
    "sweep",
    "search",
    "review",
    "refactor",
    "remove",
    "replace",
    "delete",
    "patch",
    "repair",
    "address",
    "resolve",
}

SCOPE_VERBS_FA: set[str] = {
    "پیدا",
    "جستجو",
    "سرچ",
    "فیکس",
    "درست",
    "اصلاح",
    "آپدیت",
    "بررسی",
    "چک",
    "rename",
    "منتقل",
    "جایگزین",
    "حذف",
    "پاک",
    "وریفای",
    "ریویو",
    "audit",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _tokenize(text: str) -> list[str]:
    return _normalize(text).split(" ")


def _find_verb_positions(tokens: list[str], verb: str) -> list[int]:
    verb_tokens = verb.split(" ")
    n = len(verb_tokens)
    hits: list[int] = []
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] == verb_tokens:
            hits.append(i)
    return hits


def _scan(tokens: list[str], vocab: dict[str, list[str]]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for verb in vocab:
        positions = _find_verb_positions(tokens, verb.lower())
        if positions:
            found[verb] = positions
    return found


def _scan_scope(tokens: list[str], vocab: set[str]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for verb in vocab:
        positions = _find_verb_positions(tokens, verb.lower())
        if positions:
            found[verb] = positions
    return found


def _current_session_id() -> str:
    sid_path = os.environ.get("COS_SESSION_FILE")
    if not sid_path:
        base = os.environ.get("COS_AGENT_DIR")
        if base:
            sid_path = str(Path(base) / "session-id")
    if not sid_path:
        return ""
    try:
        return Path(sid_path).read_text().strip()[:64]
    except OSError:
        return ""


def extract_intent(prompt: str) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        return _empty_result(prompt)

    tokens = _tokenize(prompt)

    matched_ex_fa = _scan(tokens, EXHAUSTIVE_VERBS_FA)
    matched_ex_en = _scan(tokens, EXHAUSTIVE_VERBS_EN)
    matched_scope_en = _scan_scope(tokens, SCOPE_VERBS_EN)
    matched_scope_fa = _scan_scope(tokens, SCOPE_VERBS_FA)

    all_ex_positions: list[tuple[str, int]] = []
    for verb, positions in {**matched_ex_fa, **matched_ex_en}.items():
        all_ex_positions.extend((verb, p) for p in positions)

    all_scope_positions: list[int] = []
    for positions in {**matched_scope_en, **matched_scope_fa}.values():
        all_scope_positions.extend(positions)

    matched_ex_within_window: list[str] = []
    for verb, ex_pos in all_ex_positions:
        if any(abs(ex_pos - sp) <= WINDOW_TOKENS for sp in all_scope_positions):
            matched_ex_within_window.append(verb)

    exhaustive = bool(matched_ex_within_window) and bool(all_scope_positions)

    predicates: set[str] = set()
    if exhaustive:
        for verb in matched_ex_within_window:
            predicates.update(EXHAUSTIVE_VERBS_FA.get(verb, []) + EXHAUSTIVE_VERBS_EN.get(verb, []))

    matched_scope_verbs = sorted(set(matched_scope_en) | set(matched_scope_fa))

    return {
        "exhaustive": exhaustive,
        "matched_exhaustive": sorted(set(matched_ex_within_window)),
        "matched_scope": matched_scope_verbs,
        "predicates": sorted(predicates),
        "prompt_length": len(prompt),
        "token_count": len(tokens),
        "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": _current_session_id(),
    }


def _empty_result(prompt: str) -> dict[str, Any]:
    return {
        "exhaustive": False,
        "matched_exhaustive": [],
        "matched_scope": [],
        "predicates": [],
        "prompt_length": len(prompt or ""),
        "token_count": 0,
        "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": _current_session_id(),
    }


def _intent_file_path() -> Path | None:
    # Panel-first (TASK-107): .intent.json is per-panel so two panels of the
    # same agent don't clobber each other's exhaustive-scope intent. The
    # completion guardian reads COS_PANEL_DIR first (agent-dir fallback), so
    # the writer must match. Fall back to COS_AGENT_DIR when no panel is set.
    panel = os.environ.get("COS_PANEL_DIR")
    if panel:
        return Path(panel) / ".intent.json"
    base = os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base) / ".intent.json"
    state = os.environ.get("COS_STATE_DIR") or ".coding-os"
    agent = os.environ.get("COS_AGENT") or "claude"
    return Path(state) / agent / ".intent.json"


def _write_intent_safe(target: Path, result: dict[str, Any]) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    except OSError as exc:
        sys.stderr.write(f"intent-write-failed: {exc}\n")


def main(argv: list[str]) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    prompt = payload.get("prompt") or payload.get("user_prompt") or ""
    if not isinstance(prompt, str):
        prompt = ""

    result = extract_intent(prompt)

    target = _intent_file_path()
    if target is not None:
        _write_intent_safe(target, result)

    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
