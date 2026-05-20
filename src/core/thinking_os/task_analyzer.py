"""Phase N — Task Analyzer."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from cognition_schemas import TaskSignals

# ---------------------------------------------------------------------------
# Tunables (read from .coding-os/config.yaml cognition section if present)
# ---------------------------------------------------------------------------

_DEFAULT_ANALYZER_TIMEOUT_MS = 500
_DEFAULT_PER_SIGNAL_TIMEOUT_MS = 200
_DEFAULT_GIT_TIMEOUT_S = 0.2
_TAKEOVER_CACHE_TTL_S = 24 * 3600

# ---------------------------------------------------------------------------
# Domain + action keyword maps (data-driven, easy to extend)
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "backend": ["api", "endpoint", "route", "server", "service", "handler", "controller"],
    "frontend": ["component", "page", "ui", "ux", "react", "next", "tailwind", "jsx", "tsx"],
    "db": ["schema", "migration", "table", "column", "sql", "postgres", "sqlite", "index"],
    "infra": ["docker", "compose", "kubernetes", "k8s", "terraform", "ansible", "ci/cd"],
    "devops": ["pipeline", "deploy", "release", "artifact", "rollout", "canary"],
    "observability": [
        "log",
        "trace",
        "metric",
        "alert",
        "dashboard",
        "grafana",
        "prometheus",
        "sentry",
    ],
    "security": ["auth", "security", "vulnerability", "csrf", "xss", "sql injection", "encrypt"],
    "auth": ["auth", "jwt", "oauth", "token", "login", "session", "password"],
    "ai-ml": ["model", "llm", "embedding", "prompt", "rag", "fine-tune"],
    "docs": ["docs", "documentation", "readme", "adr", "playbook"],
    "mobile": ["ios", "android", "react-native", "flutter", "mobile"],
}

_ACTION_VERBS: dict[str, list[str]] = {
    "create": ["add", "build", "create", "implement", "introduce", "new", "scaffold", "integrate"],
    "modify": ["update", "modify", "change", "adjust", "extend", "tweak", "rename"],
    "debug": ["fix", "debug", "bug", "error", "broken", "failing", "crash", "regression"],
    "research": ["research", "investigate", "explore", "evaluate", "compare", "spike", "prototype"],
    "review": ["code review", "pr review", "review the code", "inspect", "verify"],
    "deploy": ["deploy", "release", "ship", "rollout", "launch"],
    "refactor": ["refactor", "cleanup", "reorganize", "simplify", "consolidate"],
    "document": ["document", "describe", "write docs", "readme", "adr"],
    "audit": ["audit", "scan", "vet", "penetration", "security review"],
}

_EXTERNAL_DEP_TOKENS = [
    "stripe",
    "twilio",
    "sendgrid",
    "oauth",
    "jwt",
    "kms",
    "sns",
    "sqs",
    "auth0",
    "okta",
    "cognito",
    "firebase",
    "sentry",
    "datadog",
    "openai",
    "anthropic",
    "google",
    "gcp",
    "aws",
    "azure",
    "api key",
    "api token",
    "access token",
    "sdk",
]

_INCIDENT_TOKENS = [
    "incident",
    "pager",
    "paged",
    "asap",
    "production down",
    "prod down",
    "s0",
    "s1",
    "severity 0",
    "severity 1",
    "outage",
    "on fire",
]

_UNKNOWN_TOKENS = ["not sure", "maybe", "tbd", "todo", "unclear", "??", "probably", "might"]

_BREAKING_TOKENS = [
    "breaking change",
    "backwards incompatible",
    "schema change",
    "remove column",
    "drop table",
    "rename endpoint",
    "deprecate",
]

_PROD_IMPACT_TOKENS = [
    "production",
    "customer facing",
    "user facing",
    "live",
    "in prod",
    "revenue",
    "payment",
    "billing",
]

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_task(
    prompt: str,
    task_marker: str | None = None,
    complexity: str = "COMPLICATED",
    dimensions: int = 1,
    *,
    agent_dir: Path | None = None,
    project_dir: Path | None = None,
    mcp_hooks: dict[str, Any] | None = None,
) -> TaskSignals:
    t0 = time.time()
    source_errors: list[str] = []
    evidence: dict[str, Any] = {"prompt_len": len(prompt)}

    # Cache check ------------------------------------------------------------
    cache_path = _cache_path(agent_dir, task_marker)
    if cache_path is not None:
        cached = _read_cache(cache_path, task_marker)
        if cached is not None:
            return cached

    lowered = prompt.lower()

    # 1. Action (static verb classifier) -------------------------------------
    action = _extract_action(lowered)

    # 2. Domain (static keyword match) ---------------------------------------
    domains = _extract_domains(lowered)

    # 3. Urgency --------------------------------------------------------------
    urgency = _extract_urgency(lowered)

    # 4. Has-unknowns ---------------------------------------------------------
    has_unknowns = any(tok in lowered for tok in _UNKNOWN_TOKENS)

    # 5. External dependency --------------------------------------------------
    external_dependency = any(tok in lowered for tok in _EXTERNAL_DEP_TOKENS)

    # 6. Breaking change ------------------------------------------------------
    lexical_breaking = any(tok in lowered for tok in _BREAKING_TOKENS)

    # 7. Production impact ----------------------------------------------------
    has_production_impact = any(tok in lowered for tok in _PROD_IMPACT_TOKENS)

    # 8. Scope size from dimensions ------------------------------------------
    scope_size = _scope_from_dimensions(dimensions, lowered)

    # 9. Novelty (requires cos_search) ---------------------------------------
    novelty = 0.0
    try:
        novelty = _extract_novelty(prompt, mcp_hooks)
        evidence["novelty_source"] = (
            "cos_search" if mcp_hooks and "cos_search" in mcp_hooks else "default"
        )
    except Exception as exc:
        source_errors.append(f"novelty:{type(exc).__name__}")

    # 10. Breaking change (graph impact) merged with lexical -----------------
    graph_breaking = False
    try:
        graph_breaking = _extract_breaking_via_graph(prompt, mcp_hooks)
    except Exception as exc:
        source_errors.append(f"graph_impact:{type(exc).__name__}")
    breaking_change = lexical_breaking or graph_breaking

    # 11. Is-takeover (cached, flock'd, git-based) ---------------------------
    is_takeover = False
    try:
        is_takeover = _extract_is_takeover(project_dir, mcp_hooks)
    except Exception as exc:
        source_errors.append(f"takeover:{type(exc).__name__}")

    # Assemble ----------------------------------------------------------------
    extraction_ms = int((time.time() - t0) * 1000)
    if extraction_ms > _DEFAULT_ANALYZER_TIMEOUT_MS:
        source_errors.append(f"budget_overrun:{extraction_ms}ms")

    signals = TaskSignals(
        domain=domains,
        action=action,
        novelty=novelty,
        breaking_change=breaking_change,
        has_production_impact=has_production_impact,
        has_unknowns=has_unknowns,
        urgency=urgency,
        scope_size=scope_size,
        external_dependency=external_dependency,
        is_takeover=is_takeover,
        complexity=complexity,  # type: ignore[arg-type]
        dimensions=dimensions,
        evidence=evidence,
        extraction_ms=extraction_ms,
        source_errors=source_errors,
    )

    if cache_path is not None:
        _write_cache(cache_path, task_marker, signals)
    return signals


# ---------------------------------------------------------------------------
# Per-signal extractors (private)
# ---------------------------------------------------------------------------


def _extract_action(lowered: str) -> str:
    best = ("unknown", 0)
    for action, verbs in _ACTION_VERBS.items():
        hits = sum(1 for v in verbs if re.search(rf"\b{re.escape(v)}\b", lowered))
        if hits > best[1]:
            best = (action, hits)
    return best[0]


def _extract_domains(lowered: str) -> list[str]:
    found: list[str] = []
    for domain, kws in _DOMAIN_KEYWORDS.items():
        for kw in kws:
            if re.search(rf"\b{re.escape(kw)}\b", lowered):
                found.append(domain)
                break
    return found


def _extract_urgency(lowered: str) -> str:
    if sum(1 for t in _INCIDENT_TOKENS if t in lowered) >= 2:
        return "incident"
    if any(t in lowered for t in ["urgent", "high priority", "critical", "blocker"]):
        return "elevated"
    return "normal"


def _scope_from_dimensions(dims: int, lowered: str) -> str:
    if "recursive" in lowered or "decompose" in lowered:
        return "recursive"
    if dims <= 1:
        return "trivial"
    if dims <= 3:
        return "small"
    if dims <= 6:
        return "medium"
    if dims <= 8:
        return "large"
    return "recursive"


def _extract_novelty(prompt: str, mcp_hooks: dict[str, Any] | None) -> float:
    """Query cos_search for the top-level noun phrases; low hits = high novelty."""
    if not mcp_hooks or "cos_search" not in mcp_hooks:
        return 0.5  # neutral default when no memory available
    # Cheap query — first 80 chars of prompt keep it short
    hook = mcp_hooks["cos_search"]
    query = prompt[:80].strip()
    try:
        results = hook(query=query, limit=10)  # returns list or envelope
    except Exception:
        return 0.5
    count = 0
    if isinstance(results, dict):
        data = results.get("data") or {}
        count = len(data.get("results") or data.get("items") or [])
    elif isinstance(results, list):
        count = len(results)
    return max(0.0, min(1.0, 1.0 - count / 10.0))


def _extract_breaking_via_graph(prompt: str, mcp_hooks: dict[str, Any] | None) -> bool:
    """Use cos_graph_impact to detect blast radius ≥ 5 reverse-deps."""
    if not mcp_hooks or "cos_graph_impact" not in mcp_hooks:
        return False
    # Pull symbol-ish tokens (CamelCase / snake_case) from prompt
    symbols = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\b", prompt)[:3]
    if not symbols:
        return False
    hook = mcp_hooks["cos_graph_impact"]
    try:
        for sym in symbols:
            res = hook(target=sym, depth=3)
            data = res.get("data", {}) if isinstance(res, dict) else {}
            reverse_deps = data.get("reverse_deps") or data.get("impacts") or []
            if len(reverse_deps) >= 5:
                return True
    except Exception:
        return False
    return False


def _extract_is_takeover(project_dir: Path | None, _mcp_hooks: dict[str, Any] | None) -> bool:
    """Check flock'd 24h cache first; on miss run time-boxed git log."""
    if project_dir is None:
        return False
    cache = project_dir / ".coding-os" / ".takeover-verdict"
    # Cache hit?
    if cache.exists():
        try:
            age = time.time() - cache.stat().st_mtime
            if age < _TAKEOVER_CACHE_TTL_S:
                return cache.read_text().strip() == "true"
        except OSError:
            pass

    # Compute (best-effort, time-boxed)
    verdict = _compute_takeover_verdict(project_dir)

    # Write under flock to prevent concurrent thrash
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        _flock_write(cache, "true" if verdict else "false")
    except OSError:
        pass
    return verdict


def _compute_takeover_verdict(project_dir: Path) -> bool:
    """True if >1 author recently + low doc density."""
    # 1. Recent authors
    source_paths = _source_paths(project_dir)
    if not source_paths:
        return False
    try:
        result = subprocess.run(
            ["git", "log", "--since=30.days", "--format=%ae", "--", *source_paths],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=_DEFAULT_GIT_TIMEOUT_S,
        )
        if result.returncode != 0:
            return False
        authors = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

    # 2. Doc density
    docs_dir = project_dir / "docs"
    if not docs_dir.exists():
        return len(authors) > 1
    try:
        docs_count = sum(1 for _ in docs_dir.rglob("*.md"))
    except OSError:
        docs_count = 0
    code_count = 0
    for sp in source_paths:
        p = project_dir / sp
        if not p.exists():
            continue
        try:
            code_count += sum(1 for _ in p.rglob("*.py"))
            code_count += sum(1 for _ in p.rglob("*.ts"))
            code_count += sum(1 for _ in p.rglob("*.tsx"))
        except OSError:
            continue
    ratio = docs_count / max(code_count, 1)
    return len(authors) > 1 and ratio < 0.3


def _source_paths(project_dir: Path) -> list[str]:
    """Return source dirs from stack.yaml or canonical fallbacks."""
    stack_yaml = project_dir / "stack.yaml"
    if stack_yaml.exists():
        try:
            import yaml

            data = yaml.safe_load(stack_yaml.read_text()) or {}
            paths = data.get("source_paths")
            if isinstance(paths, list) and paths:
                return [str(p) for p in paths]
        except Exception:
            pass
    canonical = ["src", "core", "backend", "frontend", "cli", "app"]
    return [p for p in canonical if (project_dir / p).is_dir()]


# ---------------------------------------------------------------------------
# Cache helpers (flock-safe)
# ---------------------------------------------------------------------------


def _cache_path(agent_dir: Path | None, task_marker: str | None) -> Path | None:
    if agent_dir is None or task_marker is None:
        return None
    return agent_dir / ".signals"


def _read_cache(cache: Path, task_marker: str) -> TaskSignals | None:
    if not cache.exists():
        return None
    try:
        raw = json.loads(cache.read_text())
    except (OSError, ValueError):
        return None
    if raw.get("_task_marker") != task_marker:
        return None
    raw.pop("_task_marker", None)
    try:
        return TaskSignals(**raw)
    except Exception:
        return None


def _write_cache(cache: Path, task_marker: str, signals: TaskSignals) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        payload = signals.model_dump()
        payload["_task_marker"] = task_marker
        _flock_write(cache, json.dumps(payload))
    except OSError:
        pass


def _flock_write(path: Path, content: str) -> None:
    """POSIX advisory-lock write. Falls back to plain write on Windows."""
    try:
        import fcntl

        lock_path = path.with_suffix(path.suffix + ".lock")
        with open(lock_path, "w") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            try:
                path.write_text(content)
            finally:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        # Best-effort cleanup of lock file
        try:
            os.unlink(lock_path)
        except OSError:
            pass
    except ImportError:
        path.write_text(content)
