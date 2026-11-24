"""Read a review role's output: its verdict, its findings and the paths it cited.

Shared by the detached dispatch (auto_dispatch.py) and the native subagent
(native_review.py), so both paths record a review the same way.
Contract: docs/engineering/agent-supervision.md § The review gate.
"""

from __future__ import annotations

import json
import re
from typing import Any

from board_os.review_gate import DETAIL_CHARS

_PATH_RE = re.compile(r"\b(?:src|tests|docs|scripts)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}\b")
_FINDING_KEYS = ("review_findings", "findings", "dependency_risks")
# `detail` is the reviewer's contract key (reviewer.md), `description` the auditor's.
_TEXT_KEYS = ("description", "detail", "finding", "issue", "summary", "title", "message")
_FENCED = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def parse_output(message: str) -> dict[str, Any] | None:
    candidates = [message.strip(), *reversed(_FENCED.findall(message))]
    if "{" in message and "}" in message:
        candidates.append(message[message.index("{") : message.rindex("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_verdict(output_json: object) -> tuple[bool | None, list[str]]:
    # A review that ran and found nothing reads identically to a review whose
    # findings were dropped, unless the verdict travels with the route. The
    # route and the price used to be the whole message the parent got back.
    if not isinstance(output_json, dict):
        return None, []
    passed = output_json.get("passed")
    passed = passed if isinstance(passed, bool) else None

    findings: list[str] = []
    for key in _FINDING_KEYS:
        for item in output_json.get(key) or []:
            text = finding_text(item)
            if text:
                findings.append(text)
    # Uncut: review_gate.record orders by severity before it applies the one cap.
    return passed, findings


def finding_text(item: object) -> str:
    if isinstance(item, str):
        return item[:DETAIL_CHARS]
    if not isinstance(item, dict):
        return ""
    body = next((str(item[k]) for k in _TEXT_KEYS if item.get(k)), "")
    if not body:
        return ""
    if item.get("file"):
        line = f":{item['line']}" if item.get("line") else ""
        body = f"{item['file']}{line} — {body}"
    severity = item.get("severity")
    prefix = f"{severity}: " if isinstance(severity, str) and severity else ""
    return (prefix + body)[:DETAIL_CHARS]


def cited_paths(output_json: object, raw_transcript: str | None) -> set[str]:
    # The reviewer's own words are the evidence. Scan the transcript as well as
    # the structured output: a role that names files only in prose still told
    # us where it looked.
    haystack = json.dumps(output_json, default=str) if output_json else ""
    if raw_transcript:
        haystack = f"{haystack}\n{raw_transcript}"
    return set(_PATH_RE.findall(haystack))


def scope_verdict(cited: set[str], allowed: set[str]) -> str | None:
    # None means "no verdict" — recorded normally. A guard that fires on the
    # absence of evidence gets routed around, so both unknowns stay silent: a
    # role that cites nothing may legitimately have no file to name, and an
    # empty allowed set is a claim we cannot test rather than one that failed.
    if not cited or not allowed:
        return None
    if cited & allowed:
        return None
    return (
        f"out of scope: cited {len(cited)} path(s), none inside the "
        f"{len(allowed)} the task changed. cited={sorted(cited)[:5]} "
        f"allowed={sorted(allowed)[:5]}"
    )
