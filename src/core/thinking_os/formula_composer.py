"""Phase N — Formula Composer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml
from cognition_schemas import ComposedChain, RoleActivation, TaskSignals

_HERE = Path(__file__).resolve().parent
_ROLES_DIR = _HERE / "roles"
_PRESETS_FILE = _HERE / "presets" / "registry.yaml"
_SITUATIONS_FILE = _HERE / "situations" / "registry.yaml"

# Canonical role ordering — data-driven from agents/<role>.md frontmatter
# `canonical_order: N` field. Sorted ascending; ties broken alphabetically.
# Adding a new role requires only a frontmatter entry — no edit here.
_CANONICAL_ORDER_FALLBACK: list[str] = [
    "researcher",
    "analyst",
    "architect",
    "documenter",
    "implementer",
    "reviewer",
    "debugger",
    "security_auditor",
    "deployer",
    "observer",
    "refactorer",
]


def _load_canonical_order() -> list[str]:
    """Read agents/<role>.md frontmatter `canonical_order:` and sort."""
    try:
        import yaml as _yaml  # type: ignore
    except ImportError:
        return list(_CANONICAL_ORDER_FALLBACK)
    agents_dir = _HERE / "agents"
    if not agents_dir.exists():
        return list(_CANONICAL_ORDER_FALLBACK)

    entries: list[tuple[int, str]] = []
    for md in sorted(agents_dir.glob("*.md")):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            meta = _yaml.safe_load(parts[1]) or {}
            order = meta.get("canonical_order")
            if not isinstance(order, int):
                continue
            rid = str(meta.get("id") or md.stem)
            entries.append((order, rid))
        except (OSError, _yaml.YAMLError):
            continue

    if not entries:
        return list(_CANONICAL_ORDER_FALLBACK)
    return [rid for _, rid in sorted(entries)]


_CANONICAL_ORDER: list[str] = _load_canonical_order()
_CANONICAL_INDEX: dict[str, int] = {r: i for i, r in enumerate(_CANONICAL_ORDER)}

_HARD_FALLBACK: dict[str, list[str]] = {
    "CLEAR": ["implementer", "reviewer"],
    "COMPLICATED": ["analyst", "architect", "implementer", "reviewer"],
    "COMPLEX": ["researcher", "analyst", "architect", "implementer", "reviewer"],
    "CHAOTIC": ["debugger", "reviewer"],
    "CONFUSION": ["analyst", "implementer", "reviewer"],
}

_DEFAULT_PRESET_MIN_SCORE = 8

_roles_cache: dict[str, dict] | None = None
_presets_cache: list[dict] | None = None
_preset_version_cache: str | None = None
_situations_cache: dict[str, dict] | None = None


def reset_registry_cache() -> None:
    """Clear in-process caches (useful for tests or SIGHUP-driven reload)."""
    global _roles_cache, _presets_cache, _preset_version_cache, _situations_cache
    _roles_cache = None
    _presets_cache = None
    _preset_version_cache = None
    _situations_cache = None


def load_roles() -> dict[str, dict]:
    """Load all role yaml files into a dict keyed by role id.

    Filenames are now semantic (researcher.yaml, analyst.yaml, ...). The
    role id inside each file is the same slug; we ignore README.md and
    similar non-role yaml files.
    """
    global _roles_cache
    if _roles_cache is not None:
        return _roles_cache
    roles: dict[str, dict] = {}
    if _ROLES_DIR.is_dir():
        for path in sorted(_ROLES_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
                if "id" in data:
                    roles[data["id"]] = data
            except Exception as exc:
                raise RuntimeError(f"Invalid role file {path.name}: {exc}") from exc
    override_dir = _find_override_dir("roles.override")
    if override_dir is not None:
        for path in sorted(override_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
                rid = data.get("id")
                if rid and rid in roles:
                    _deep_merge(roles[rid], data)
            except Exception:
                continue
    _roles_cache = roles
    return roles


def load_presets() -> tuple[list[dict], str]:
    """Return (presets_list, version_sha256). Version stamps ComposedChain."""
    global _presets_cache, _preset_version_cache
    if _presets_cache is not None and _preset_version_cache is not None:
        return _presets_cache, _preset_version_cache
    presets: list[dict] = []
    version = ""
    raw = b""
    if _PRESETS_FILE.exists():
        raw = _PRESETS_FILE.read_bytes()
        version = hashlib.sha256(raw).hexdigest()[:16]
        try:
            data = yaml.safe_load(raw.decode("utf-8")) or {}
            presets = list(data.get("presets") or [])
        except Exception as exc:
            raise RuntimeError(f"Invalid presets registry: {exc}") from exc
    override_dir = _find_override_dir("presets.override")
    if override_dir is not None:
        for path in sorted(override_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
                extras = data.get("presets") or []
                if isinstance(extras, list):
                    presets.extend(extras)
                raw += path.read_bytes()
            except Exception:
                continue
        if raw:
            version = hashlib.sha256(raw).hexdigest()[:16]
    _presets_cache = presets
    _preset_version_cache = version
    return presets, version


def load_situations() -> dict[str, dict]:
    """Load situations registry (keyed by id). Returns empty dict on error."""
    global _situations_cache
    if _situations_cache is not None:
        return _situations_cache
    situations: dict[str, dict] = {}
    if _SITUATIONS_FILE.exists():
        try:
            data = yaml.safe_load(_SITUATIONS_FILE.read_text()) or {}
            for sit in data.get("situations") or []:
                if "id" in sit:
                    situations[sit["id"]] = sit
        except Exception:
            situations = {}
    _situations_cache = situations
    return situations


# Action keyword → TaskSignals.action. Order matters: earlier wins on a tie
# (debug/audit/review beat the generic create/modify so a "fix the failing
# test" prompt routes to debugger, not implementer). Bilingual (fa+en) since
# the repo's prompts are mixed.
_ACTION_PATTERNS: list[tuple[str, str]] = [
    ("debug", r"\b(debug|diagnose|root[- ]?cause|stack[- ]?trace|failing|broken|crash|باگ|دیباگ|خطا|اشکال)\b"),
    ("audit", r"\b(audit|security review|pentest|vulnerab|cve|threat model|ممیزی|امنیت)\b"),
    ("review", r"\b(review|code[- ]?review|critique|assess|بازبینی|مرور)\b"),
    ("research", r"\b(research|investigate|explore|best way|compare|evaluate|spike|تحقیق|بررسی|کاوش)\b"),
    ("refactor", r"\b(refactor|clean ?up|restructure|simplify|deduplicate|ریفکتور|بازنویسی)\b"),
    ("document", r"\b(document|write docs|readme|changelog|adr|مستند|داکیومنت)\b"),
    ("deploy", r"\b(deploy|release|ship|rollout|ci/cd|pipeline|دیپلوی|انتشار)\b"),
    ("create", r"\b(add|create|implement|build|new |feature|بساز|اضافه|پیاده)\b"),
    ("modify", r"\b(fix|update|change|modify|edit|adjust|tweak|اصلاح|تغییر|آپدیت)\b"),
]

# Domain keyword → TaskSignals.domain entries. Mirrors cos_classify_prompt's
# domain_patterns (kept in sync; that tool sets the gate, this sets the chain).
_DOMAIN_PATTERNS: dict[str, str] = {
    "security": r"\b(security|auth|permission|csrf|xss|sql injection|jwt|oauth|tls|encryption|secret)\b",
    "backend": r"\b(api|backend|server|django|fastapi|fiber|endpoint|router|service|mcp tool)\b",
    "frontend": r"\b(frontend|react|next\.?js|nextjs|component|ui|client|page|jsx|tsx)\b",
    "db": r"\b(database|sql|sqlite|postgres|mysql|migration|schema|index|query)\b",
    "infra": r"\b(deploy|ci/cd|docker|kubernetes|k8s|infra|hook|registry|adapter)\b",
    "docs": r"\b(doc|documentation|readme|spec|playbook|adr)\b",
    "graph": r"\b(graph|node|edge|traversal|extractor)\b",
}


def signals_from_prompt(
    prompt: str,
    complexity: str = "COMPLICATED",
    dimensions: int = 1,
) -> TaskSignals:
    """Build a RICH TaskSignals from raw prompt text.

    The auto-compose hook previously passed only complexity+dimensions, leaving
    action='unknown' / domain=[] — under which only `analyst` ever clears its
    min_score, so every task composed the identical ['analyst'] chain. This
    derives action, domain, scope_size, novelty, urgency from the prompt so the
    composer can actually discriminate (debug→debugger, security→security_auditor,
    docs→documenter, …). Deterministic; no LLM call. (TASK-057)
    """
    import re as _re

    text = (prompt or "").strip().lower()
    action = "unknown"
    for act, pat in _ACTION_PATTERNS:
        if _re.search(pat, text):
            action = act
            break

    domains = [name for name, pat in _DOMAIN_PATTERNS.items() if _re.search(pat, text)]

    # scope_size from prompt length + breadth keywords.
    words = len(text.split())
    if _re.search(r"\b(everywhere|all |every |entire|whole|across|سراسر|همه|تمام)\b", text) or words > 200:
        scope_size = "large"
    elif words < 12:
        scope_size = "small"
    else:
        scope_size = "medium"

    novelty = 0.6 if action == "research" or _re.search(
        r"\b(novel|unknown|first time|from scratch|greenfield|نامعلوم|جدید)\b", text
    ) else 0.0
    urgency = "incident" if _re.search(
        r"\b(p0|p1|outage|down|emergency|urgent|asap|hotfix|فوری|اضطرار)\b", text
    ) else "normal"
    has_unknowns = bool(_re.search(r"\b(unknown|not sure|unclear|investigate|نامعلوم|مطمئن نیستم)\b", text))

    return TaskSignals(
        complexity=complexity if complexity in {"CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC", "CONFUSION"} else "COMPLICATED",
        dimensions=max(1, dimensions),
        action=action,  # type: ignore[arg-type]
        domain=domains,
        scope_size=scope_size,  # type: ignore[arg-type]
        novelty=novelty,
        urgency=urgency,  # type: ignore[arg-type]
        has_unknowns=has_unknowns,
    )


def compose_chain(
    signals: TaskSignals,
    situation_id: str | None = None,
    preset_min_score: int | None = None,
) -> ComposedChain:
    threshold = _resolve_threshold(preset_min_score)

    if situation_id:
        situations = load_situations()
        sit = situations.get(situation_id)
        if sit:
            chain = _extract_situation_chain(sit)
            if chain:
                return ComposedChain(
                    chain=chain,
                    source="situation",
                    situation_id=situation_id,
                    preset_version=None,
                    effective_threshold=threshold,
                    reason=f"situation override: {situation_id}",
                )

    presets, preset_version = load_presets()
    best_preset = _match_best_preset(signals, presets, threshold)
    if best_preset is not None:
        chain = list(best_preset.get("chain") or [])
        parallel_layers = best_preset.get("parallel_layers") or []
        if chain:
            return ComposedChain(
                chain=chain,
                source="preset",
                preset_id=best_preset.get("id"),
                preset_version=preset_version,
                effective_threshold=threshold,
                parallel_roles=parallel_layers if best_preset.get("parallel") else [],
                reason=f"preset match: {best_preset.get('id')} score={best_preset.get('score')}",
            )

    activations = score_all_roles(signals)
    roles = load_roles()
    active = [
        a
        for a in activations
        if a.score >= int((roles.get(a.role_id) or {}).get("activation", {}).get("min_score", 1))
    ]
    if active:
        chain = _order_canonical([a.role_id for a in active])
        return ComposedChain(
            chain=chain,
            source="composer",
            preset_version=preset_version,
            effective_threshold=threshold,
            activations=active,
            reason=f"composer scoring: {len(active)} roles activated",
        )

    chain = _HARD_FALLBACK.get(signals.complexity, ["analyst", "implementer", "reviewer"])
    return ComposedChain(
        chain=chain,
        source="fallback",
        preset_version=preset_version,
        effective_threshold=threshold,
        reason=f"fallback for complexity={signals.complexity} — no preset/composer hit",
    )


def score_all_roles(signals: TaskSignals) -> list[RoleActivation]:
    """Score every role file against the signals. Returns sorted by score desc."""
    roles = load_roles()
    out: list[RoleActivation] = []
    for rid, role in roles.items():
        activation = role.get("activation") or {}
        matched: list[str] = []
        skipped: list[str] = []
        score = 0
        for trig in activation.get("primary_triggers") or []:
            if _trigger_matches(trig, signals):
                score += int(trig.get("weight", 1))
                matched.append(_trigger_desc(trig))
        for trig in activation.get("secondary_triggers") or []:
            if _trigger_matches(trig, signals):
                score += int(trig.get("weight", 1))
                matched.append(_trigger_desc(trig))
        for trig in activation.get("deactivators") or []:
            if _trigger_matches(trig, signals):
                score -= int(trig.get("weight", 1))
                skipped.append(_trigger_desc(trig))
        out.append(
            RoleActivation(
                role_id=rid,
                score=score,
                matched_triggers=matched,
                skipped_deactivators=skipped,
            )
        )
    out.sort(key=lambda a: (-a.score, _CANONICAL_INDEX.get(a.role_id, 999)))
    return out


def _trigger_matches(trig: dict, signals: TaskSignals) -> bool:
    """Evaluate a single trigger against signals. Returns True if matched."""
    sig_name = trig.get("signal")
    if sig_name is None:
        return False
    val = getattr(signals, sig_name, None)
    if "equals" in trig:
        return val == trig["equals"]
    if "in" in trig:
        expected = trig["in"]
        if isinstance(val, list):
            return any(item in expected for item in val)
        return val in expected
    if "contains" in trig:
        needed = trig["contains"]
        if not isinstance(val, list):
            return False
        if isinstance(needed, list):
            return any(item in val for item in needed)
        return needed in val
    if "gte" in trig:
        try:
            return float(val) >= float(trig["gte"])
        except (TypeError, ValueError):
            return False
    if "lte" in trig:
        try:
            return float(val) <= float(trig["lte"])
        except (TypeError, ValueError):
            return False
    return False


def _trigger_desc(trig: dict) -> str:
    parts = [str(trig.get("signal", "?"))]
    for op in ("equals", "in", "contains", "gte", "lte"):
        if op in trig:
            parts.append(f"{op}={trig[op]!r}")
            break
    return ":".join(parts)


def _match_best_preset(signals: TaskSignals, presets: list[dict], threshold: int) -> dict | None:
    candidates: list[tuple[int, dict]] = []
    for preset in presets:
        match = preset.get("match") or {}
        if not match:
            continue
        if not _preset_match_satisfied(match, signals):
            continue
        score = int(preset.get("score", 0))
        if score < threshold:
            continue
        candidates.append((score, preset))
    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]


def _preset_match_satisfied(match: dict, signals: TaskSignals) -> bool:
    for key, expected in match.items():
        if key.endswith("_any"):
            field = key[:-4]
            val = getattr(signals, field, None)
            if not isinstance(val, list):
                return False
            if not any(item in val for item in expected):
                return False
        elif key.endswith("_in"):
            field = key[:-3]
            val = getattr(signals, field, None)
            if val not in expected:
                return False
        elif key.endswith("_gte"):
            field = key[:-4]
            val = getattr(signals, field, None)
            try:
                if float(val) < float(expected):
                    return False
            except (TypeError, ValueError):
                return False
        elif key.endswith("_lte"):
            field = key[:-4]
            val = getattr(signals, field, None)
            try:
                if float(val) > float(expected):
                    return False
            except (TypeError, ValueError):
                return False
        else:
            val = getattr(signals, key, None)
            if isinstance(val, list) and isinstance(expected, list):
                if not any(item in val for item in expected):
                    return False
            elif val != expected:
                return False
    return True


def _order_canonical(role_ids: list[str]) -> list[str]:
    """Sort into canonical researcher→refactorer order, dedup."""
    seen: set[str] = set()
    ordered: list[str] = []
    for rid in sorted(role_ids, key=lambda r: _CANONICAL_INDEX.get(r, 999)):
        if rid not in seen:
            seen.add(rid)
            ordered.append(rid)
    return ordered


def _extract_situation_chain(sit: dict) -> list[str]:
    """Pull formula IDs from a situation's dispatch_chain."""
    chain: list[str] = []
    for step in sit.get("dispatch_chain") or []:
        if isinstance(step, dict) and "dispatch" in step:
            chain.append(str(step["dispatch"]))
    return chain


def _resolve_threshold(override: int | None) -> int:
    """Read threshold: explicit override > .coding-os/config.yaml > default."""
    if override is not None:
        return max(0, min(15, int(override)))
    cfg = _find_project_config()
    if cfg is not None:
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
            val = (data.get("cognition") or {}).get("preset_min_score")
            if val is not None:
                return max(0, min(15, int(val)))
        except Exception:
            pass
    return _DEFAULT_PRESET_MIN_SCORE


def _find_project_config() -> Path | None:
    for base in _candidate_project_dirs():
        cfg = base / ".coding-os" / "config.yaml"
        if cfg.exists():
            return cfg
    return None


def _find_override_dir(name: str) -> Path | None:
    for base in _candidate_project_dirs():
        d = base / ".coding-os" / name
        if d.is_dir():
            return d
    return None


def _candidate_project_dirs() -> list[Path]:
    """Project dir candidates — CWD first, then up the tree, up to 4 levels."""
    out: list[Path] = []
    env = os.environ.get("COS_PROJECT_DIR")
    if env:
        out.append(Path(env))
    cwd = Path.cwd()
    out.append(cwd)
    for depth in range(1, 5):
        parent = cwd
        for _ in range(depth):
            parent = parent.parent
        out.append(parent)
    return out


def _deep_merge(base: dict, overlay: dict) -> None:
    """In-place deep merge: overlay wins on conflict; lists are replaced."""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
