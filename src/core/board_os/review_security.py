"""Whether a task's review round needs the security auditor, and the digest it records.

Contract: docs/engineering/agent-supervision.md § When the security auditor runs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from board_os.review_gate import MINOR_SEVERITIES, git_output, ledger_rows, severity

AUDITOR = "security_auditor"

# Matched lower-cased with camelCase split, so "OAuthProvider.ts" reads "oauth_provider.ts"
# and "authoring" never reads as "auth".
_IGNORED = re.compile(
    r"(^|/)(docs?|tests?|__tests__|golden)/|(^|/)test_[^/]*$"
    r"|\.(md|mdx|rst|png|jpe?g|gif|svg|webp|ico|pdf|woff2?|ttf|otf|mp4|mov|lock)$"
)
_RUNS_COMMANDS = re.compile(
    r"\.(sh|bash|zsh|ps1)$|(^|/)hooks/.*\.py$|(^|/)\.(husky|githooks|circleci)/"
    r"|(^|/)\.github/workflows/|(^|/)\.gitlab-ci\.yml$|(^|/)jenkinsfile$|(^|/)makefile$"
    r"|(^|/)\.pre-commit-config\.yaml$|(^|/)[^/]*dockerfile[^/]*$|(^|/)docker-compose[^/]*$"
)
_OUTSIDE_CODE = re.compile(
    r"(^|/)(package\.json|pyproject\.toml|setup\.(py|cfg)|requirements[^/]*\.txt|pipfile"
    r"|go\.mod|cargo\.toml|gemfile|composer\.json|pom\.xml|build\.gradle(\.kts)?)$"
)
_SECRETS = re.compile(
    r"(^|/)\.env(\.[^/]*)?$|(^|/)\.(claude|codex)/settings[^/]*\.json$"
    r"|(^|/)\.codex/config\.toml$|(^|/)\.mcp\.json$"
)
_ACCESS = re.compile(
    r"(?<![a-z])(auth|authn|authz|authentication|authorization|oauth\d*|login|logout|signin"
    r"|signup|tokens?|jwt|secrets?|credentials?|passwords?|passwd|permissions?|rbac|crypto"
    r"|cipher|csrf|cors|sanitiz\w*|tls|ssl|certs?|certificates?|security)(?![a-z])"
)
_SENSITIVE = (_RUNS_COMMANDS, _OUTSIDE_CODE, _SECRETS, _ACCESS)


def security_files(files: list[str]) -> list[str]:
    return [path for path in files if _sensitive(path)]


def _sensitive(path: str) -> bool:
    lowered = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", path).lower()
    if _IGNORED.search(lowered):
        return False
    return any(pattern.search(lowered) for pattern in _SENSITIVE)


def audit_digest(
    task_id: str,
    round_no: int,
    project_root: Path,
    scope: dict[str, Any],
    *,
    path: Path | None = None,
) -> str:
    # "" when this round needs no audit; otherwise the digest its ledger row keeps.
    files = security_files([str(name) for name in scope.get("files") or []])
    commits = [str(sha) for sha in scope.get("commits") or []]
    if not files or not commits:
        return ""
    patch = git_output(project_root, "show", "--format=", "--patch", *commits, "--", *files)
    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()[:16]
    return digest if _due(task_id, round_no, digest, path) else ""


def _due(task_id: str, round_no: int, digest: str, path: Path | None) -> bool:
    last: dict[str, Any] | None = None
    for entry in ledger_rows(task_id, path):
        earlier = isinstance(entry.get("round"), int) and entry["round"] < round_no
        if earlier and entry.get("role") == AUDITOR and entry.get("state") == "done":
            last = entry
    if last is None or last.get("digest") != digest:
        return True
    # An unchanged diff is re-audited only to check a blocking finding was fixed;
    # same reading as the gate: no findings plus passed=false blocks.
    findings = [str(text) for text in last.get("findings") or []]
    if not findings:
        return last.get("passed") is False
    return any(severity(text) not in MINOR_SEVERITIES for text in findings)
