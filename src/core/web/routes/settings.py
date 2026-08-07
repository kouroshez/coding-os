"""core.web.routes.settings — hub-level settings read/write."""

from __future__ import annotations

import contextlib
import copy
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from thinking_os.project_settings import (
    SettingsConflictError,
    read_settings,
    settings_lock,
    write_settings,
)
from thinking_os.supervision import DEFAULT_MODEL_ROUTING, ModelRoutingPolicy, normalize_policy

logger = logging.getLogger("coding_os.web.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULTS: dict = {
    "budget_cap": {"enabled": False, "cap_usd": 5.0},
    "trace_rotation": {"gzip_age_days": 3, "delete_age_days": 30},
    "model_routing": copy.deepcopy(DEFAULT_MODEL_ROUTING),
    # Board drag auto-spawn — default OFF: a human panel drag icebox→in_progress
    # dispatches an implementer sub-session on the task (board.py::_auto_spawn_safe).
    "auto_spawn": {"enabled": False},
    # Claude auth mode (TASK-756): "subscription" (default) leaves the CLI's own
    # OAuth session in charge — byte-identical to pre-existing behavior. "api_key"
    # forwards api_key as ANTHROPIC_API_KEY into the dispatch subprocess env
    # (sdk_dispatcher.py::_claude_auth_env), which the CLI's own documented
    # precedence puts above subscription OAuth. api_key is masked on every read —
    # see _masked_settings.
    "claude_auth": {"mode": "subscription", "api_key": ""},
    # pr-mode git workflow (TASK-518) — default OFF = byte-identical to trunk.
    # enabled persists COS_GIT_WORKFLOW=pr into the agent env (cos-env.sh § pr-mode
    # enablement); integration_branch + protected_branches feed branch-guard +
    # the cos pr executor. SPEC: docs/playbooks/pr-workflow.md § 1.
    "git_settings": {
        "enabled": False,
        "integration_branch": "main",
        "protected_branches": ["production"],
        # Trust Spectrum (TASK-533): draft = human merges; auto_merge = arm on
        # green required check; autonomous = + driver auto-cleanup. Safe default.
        "autonomy_level": "draft",
        # Worktree bootstrap: gitignored paths to symlink into a fresh worktree +
        # a one-time setup command, so the agent's first validate command works.
        # Empty = no-op (byte-identical to no bootstrap).
        "worktree_include": [],
        "worktree_setup_cmd": "",
    },
}


def _settings_path() -> Path:
    # Project-scoped when a /api/p/<slug>/ request bound a root (mirror
    # current_db_path): write the bound project's OWN .coding-os/hub-settings.json,
    # never the Hub process's global COS_STATE_DIR — else a multi-project Hub
    # collapses every project's settings into one shared file and a save for
    # project A clobbers B (the toggle then never reaches A's agent).
    from web._project_context import current_project_root, is_explicit_project_scope

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os" / "hub-settings.json"
    state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
    return Path(state_dir) / "hub-settings.json"


def _read_raw() -> tuple[dict, bool]:
    # (raw, corrupt). corrupt=True only when the file EXISTS but is unparseable or
    # not a JSON object — so a write path can refuse rather than clobber a present
    # but momentarily-unreadable file with all-defaults.
    try:
        return read_settings(_settings_path()), False
    except SettingsConflictError as exc:
        logger.debug("hub-settings.json load error: %s", exc)
        return {}, True


def _merge_defaults(raw: dict) -> dict:
    # Start from raw so sections NOT in _DEFAULTS (e.g. task_closure, or any future
    # subsystem's section) survive the round-trip; then overlay defaults for the
    # known sections. Without the {**raw} seed, _load drops every unknown section
    # and the next PATCH writes it away (silent data loss).
    merged: dict = {**raw}
    for section, defaults in _DEFAULTS.items():
        merged[section] = {**defaults, **(raw.get(section) or {})}
    raw_routing = raw.get("model_routing") if isinstance(raw.get("model_routing"), dict) else {}
    merged["model_routing"] = normalize_policy(raw_routing)
    return merged


def _load() -> dict:
    raw, _ = _read_raw()
    return _merge_defaults(raw)


def _save(data: dict) -> None:
    write_settings(_settings_path(), data)


@contextlib.contextmanager
def _settings_lock():
    with settings_lock(_settings_path()):
        yield


def _env_overrides() -> dict:
    overrides: dict = {}
    for var in (
        "COS_DAILY_BUDGET_USD",
        "COS_TRACE_GZIP_AGE_DAYS",
        "COS_TRACE_DELETE_AGE_DAYS",
    ):
        val = os.environ.get(var)
        if val:
            overrides[var] = val
    return overrides


def _masked_settings(data: dict) -> dict:
    # claude_auth.api_key is write-only past this point — a GET/PATCH response
    # must never echo the raw secret back to the browser. api_key_set +
    # api_key_preview (last 4 chars) let the UI show "a key is configured"
    # without round-tripping a value the frontend could accidentally re-PATCH.
    out = {**data}
    auth = out.get("claude_auth")
    if isinstance(auth, dict):
        key = auth.get("api_key") or ""
        out["claude_auth"] = {
            "mode": auth.get("mode", "subscription"),
            "api_key_set": bool(key),
            "api_key_preview": f"...{key[-4:]}" if len(key) >= 4 else ("set" if key else ""),
        }
    return out


@router.get("")
def get_settings():
    return {"data": {"settings": _masked_settings(_load()), "env_overrides": _env_overrides()}}


def _module_error(status: int, category: str, message: str, retryable: bool) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "ok": False,
            "error": {"category": category, "message": message, "retryable": retryable},
        },
    )


@router.get("/modules")
def get_modules():
    """Per-module subsystem state for the Config tab (TASK-354)."""
    try:
        from cli.module_commands import module_state_payload
        from web._project_context import current_project_root

        payload = module_state_payload(current_project_root())
    except Exception as exc:
        return _module_error(503, "unavailable", f"module registry unavailable: {exc}", True)
    return {"data": payload, "meta": {"layer": "settings", "source": "settings.modules"}}


@router.get("/modules/drift")
def get_module_drift():
    """Non-PASS module drift (skill/command/rule/doc/state_integrity) for a Hub WARN banner.

    Reuses the existing `cos doctor` check functions verbatim — no new check
    logic — so the toggle UI surfaces the drift its own cascade can produce
    (HUB-PB2 / TASK-504; rule/doc drift added TASK-812).
    """
    try:
        from cli.doctor import (
            SEV_PASS,
            DoctorReport,
            _check_module_command_drift,
            _check_module_doc_drift,
            _check_module_rule_drift,
            _check_module_skill_drift,
            _check_subsystems_state_integrity,
        )
        from web._project_context import current_project_root

        project = current_project_root()
        report = DoctorReport(project_dir=str(project), agent=None, templates=[])
        for check in (
            _check_module_skill_drift,
            _check_module_command_drift,
            _check_module_rule_drift,
            _check_module_doc_drift,
            _check_subsystems_state_integrity,
        ):
            check(project, report)
        drift = [
            {"id": c.id, "severity": c.severity, "message": c.message}
            for c in report.checks
            if c.severity != SEV_PASS
        ]
    except Exception as exc:
        return _module_error(503, "unavailable", f"module drift unavailable: {exc}", True)
    return {
        "data": {"drift": drift, "ok": not drift},
        "meta": {"layer": "settings", "source": "settings.modules.drift"},
    }


@router.get("/git-state")
def get_git_state(integration: str | None = None):
    """Read-only pr-mode capability + real repo git-state (branches/current/remote) for the Config Git tab."""
    try:
        from cli.pr_commands import _git_state, _integration_branch, _preflight
        from web._project_context import current_project_root

        repo = str(current_project_root())
        # Probe the branch the user is editing, not the saved one — else the
        # required_check/pr_ok pills + auto_merge warning lie while editing (M2).
        cap = _preflight(repo, integration or _integration_branch(repo))
        state = _git_state(repo)
    except Exception as exc:
        return _module_error(503, "unavailable", f"git-state unavailable: {exc}", True)
    return {"data": {**cap, **state}, "meta": {"layer": "settings", "source": "settings.git_state"}}


@router.patch("/modules/{module_id}")
def patch_module(module_id: str, body: dict = Body(...)):
    """Toggle a non-kernel module; regenerates dependent artifacts (TASK-354)."""
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return _module_error(400, "validation", "body must carry {'enabled': true|false}", False)
    try:
        from cli.module_commands import toggle_and_regen
        from web._project_context import current_project_root

        result, notes = toggle_and_regen(current_project_root(), module_id, enabled)
    except Exception as exc:
        return _module_error(503, "unavailable", f"module toggle unavailable: {exc}", True)
    if not result.ok:
        status = 404 if "unknown module" in result.reason else 400
        return _module_error(status, "validation", result.reason, False)
    return {
        "data": {"module": module_id, "enabled": enabled, "regenerated": notes},
        "meta": {"layer": "settings", "source": "settings.module_toggle"},
    }


class _BudgetCapIn(BaseModel):
    enabled: bool
    cap_usd: float


class _TraceRotationIn(BaseModel):
    gzip_age_days: int
    delete_age_days: int


class _AutoSpawnIn(BaseModel):
    enabled: bool


class _GitSettingsIn(BaseModel):
    enabled: bool
    integration_branch: str = "main"
    protected_branches: list[str] = ["production"]
    # Trust Spectrum (TASK-540/614): local = commit-only; local_autonomous = land on
    # LOCAL integration after a green verify, zero network; draft/auto_merge/autonomous
    # push. Literal rejects a typo'd rung at the API edge instead of letting it reach
    # cos-env → COS_GIT_AUTONOMY where it would silently behave as draft.
    autonomy_level: Literal["local", "local_autonomous", "draft", "auto_merge", "autonomous"] = (
        "draft"
    )
    # Explicit fields so a PATCH persists them — an exclude_unset model_dump would
    # else silently drop these as unknown keys.
    worktree_include: list[str] = []
    worktree_setup_cmd: str = ""


class _ClaudeAuthIn(BaseModel):
    mode: Literal["subscription", "api_key"] = "subscription"
    # None = field omitted from the PATCH body → leave the stored key untouched
    # (exclude_unset below drops it from the merge entirely). "" = explicit
    # clear. Non-empty = set/replace. The frontend must never round-trip the
    # masked preview back through this field.
    api_key: str | None = None


class _PatchBody(BaseModel):
    budget_cap: _BudgetCapIn | None = None
    trace_rotation: _TraceRotationIn | None = None
    model_routing: ModelRoutingPolicy | None = None
    auto_spawn: _AutoSpawnIn | None = None
    git_settings: _GitSettingsIn | None = None
    claude_auth: _ClaudeAuthIn | None = None


@router.patch("")
def patch_settings(body: _PatchBody):
    with _settings_lock():
        raw, corrupt = _read_raw()
        if corrupt:
            # Refuse rather than overwrite a present-but-unparseable file with
            # all-defaults — that would silently reset the user's pr-mode config
            # to trunk. Retryable: a torn read self-heals once the writer finishes.
            return _module_error(
                409,
                "conflict",
                "hub-settings.json is present but unreadable; refusing to overwrite. "
                "Fix or remove the file, then retry.",
                True,
            )
        current = _merge_defaults(raw)
        # Merge each provided section field-by-field (exclude_unset) so a partial
        # PATCH never resets unspecified fields to their model defaults (finding 12).
        sections = {
            "budget_cap": body.budget_cap,
            "trace_rotation": body.trace_rotation,
            "model_routing": body.model_routing,
            "auto_spawn": body.auto_spawn,
            "git_settings": body.git_settings,
            "claude_auth": body.claude_auth,
        }
        for name, model in sections.items():
            if model is not None:
                patch = model.model_dump(exclude_unset=True)
                if name == "model_routing":
                    for nested in ("orchestrator", "cooldown"):
                        if nested in patch:
                            patch[nested] = {
                                **current[name].get(nested, {}),
                                **patch[nested],
                            }
                    if "roles" in patch:
                        patch["roles"] = {
                            **current[name].get("roles", {}),
                            **{
                                role: {
                                    **current[name].get("roles", {}).get(role, {}),
                                    **target,
                                }
                                for role, target in patch["roles"].items()
                            },
                        }
                    if "orchestrator" in patch and "model" in patch["orchestrator"]:
                        patch["orchestrator_model"] = patch["orchestrator"]["model"]
                    elif "orchestrator_model" in patch:
                        patch["orchestrator"] = {
                            **current[name].get("orchestrator", {}),
                            "model": patch["orchestrator_model"],
                        }
                current[name] = {**current.get(name, {}), **patch}
        if body.model_routing is not None:
            try:
                current["model_routing"] = normalize_policy(current["model_routing"])
            except ValidationError as exc:
                return _module_error(422, "validation", str(exc), False)
        _save(current)
    return {"data": {"settings": _masked_settings(current), "env_overrides": _env_overrides()}}
