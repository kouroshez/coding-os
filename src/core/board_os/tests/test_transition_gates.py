"""Tests for core.board_os.transition_gates — schema + loader (TASK-103).

Validator behavior is tested in test_transition_gates_validator.py (TASK-104).
"""

from __future__ import annotations

import pytest

from core.board_os.transition_gates import (
    DEFAULT_GATES_PATH,
    DoRConfig,
    DoRKindRules,
    GatesConfig,
    GatesConfigError,
    OverridePolicy,
    SectionRule,
    load_gates_config,
    load_gates_from_str,
)

# ────────────────────────────────────────────────────────────────────
# Loader basics
# ────────────────────────────────────────────────────────────────────


def test_default_gates_yaml_loads_cleanly() -> None:
    """The shipped transition-gates.yaml round-trips through the schema."""
    cfg = load_gates_config()
    assert cfg.version == 1
    # 8 kinds + default = 8 explicit blocks + default
    assert "feature" in cfg.definition_of_ready.by_kind
    assert "bug" in cfg.definition_of_ready.by_kind
    assert "security" in cfg.definition_of_ready.by_kind


def test_missing_file_falls_back_to_defaults(tmp_path) -> None:
    """A missing config file yields an empty GatesConfig, not a crash."""
    cfg = load_gates_config(tmp_path / "no-such-file.yaml")
    assert isinstance(cfg, GatesConfig)
    # Default should still produce sane WIP limits.
    assert cfg.wip_limits.in_progress == 1


def test_malformed_yaml_raises_structured_error(tmp_path) -> None:
    bad = tmp_path / "gates.yaml"
    bad.write_text("not: : valid: yaml :::", encoding="utf-8")
    with pytest.raises(GatesConfigError) as exc_info:
        load_gates_config(bad)
    assert "malformed YAML" in str(exc_info.value)


def test_schema_violation_raises_structured_error() -> None:
    """A negative WIP limit fails Pydantic validation cleanly."""
    bad_yaml = """
    version: 1
    wip_limits:
      in_progress: -1
    """
    with pytest.raises(GatesConfigError) as exc_info:
        load_gates_from_str(bad_yaml)
    assert "schema violation" in str(exc_info.value)


def test_size_limits_block_below_warn_rejected() -> None:
    bad_yaml = """
    version: 1
    size_limits:
      warn_tokens: 2000
      block_tokens: 1000
    """
    with pytest.raises(GatesConfigError):
        load_gates_from_str(bad_yaml)


# ────────────────────────────────────────────────────────────────────
# DoR resolution per kind
# ────────────────────────────────────────────────────────────────────


def test_dor_for_kind_inherits_default_when_kind_block_is_empty() -> None:
    cfg = GatesConfig(
        definition_of_ready=DoRConfig(
            default=DoRKindRules(
                sections={
                    "Outcome": SectionRule(required=True, min_chars=20),
                    "Acceptance": SectionRule(required=True),
                },
            ),
            by_kind={"feature": DoRKindRules()},
        ),
    )
    rules = cfg.definition_of_ready.for_kind("feature")
    assert "Outcome" in rules.sections
    assert "Acceptance" in rules.sections
    assert rules.sections["Outcome"].min_chars == 20


def test_dor_for_kind_overrides_default_field_by_field() -> None:
    cfg = GatesConfig(
        definition_of_ready=DoRConfig(
            default=DoRKindRules(
                sections={
                    "Outcome": SectionRule(required=True, min_chars=20),
                    "Acceptance": SectionRule(required=True),
                },
            ),
            by_kind={
                "chore": DoRKindRules(
                    sections={
                        "Outcome": SectionRule(required=True, min_chars=10),
                    },
                ),
            },
        ),
    )
    rules = cfg.definition_of_ready.for_kind("chore")
    # Outcome was overridden — relaxed threshold.
    assert rules.sections["Outcome"].min_chars == 10
    # Acceptance survives from default — chore inherits it.
    assert rules.sections["Acceptance"].required is True


def test_dor_for_kind_can_explicitly_opt_out_via_null() -> None:
    """Strategic-merge-patch: kind sets section=None to drop a default rule."""
    cfg = GatesConfig(
        definition_of_ready=DoRConfig(
            default=DoRKindRules(
                sections={
                    "Outcome": SectionRule(required=True),
                    "Acceptance": SectionRule(required=True),
                },
            ),
            by_kind={
                "spike": DoRKindRules(
                    sections={
                        "Acceptance": None,  # opt out
                    },
                ),
            },
        ),
    )
    rules = cfg.definition_of_ready.for_kind("spike")
    assert "Outcome" in rules.sections
    assert "Acceptance" not in rules.sections


def test_dor_default_drops_explicit_none_entries() -> None:
    """A default rule with section=None is treated as 'unset', not 'required'."""
    cfg = GatesConfig(
        definition_of_ready=DoRConfig(
            default=DoRKindRules(
                sections={
                    "Outcome": SectionRule(required=True),
                    "Acceptance": None,  # default opts the project out
                },
            ),
        ),
    )
    rules = cfg.definition_of_ready.for_kind("anything")
    assert "Acceptance" not in rules.sections


def test_dor_unknown_kind_falls_back_to_default() -> None:
    cfg = GatesConfig(
        definition_of_ready=DoRConfig(
            default=DoRKindRules(
                sections={"Outcome": SectionRule(required=True)},
            ),
        ),
    )
    rules = cfg.definition_of_ready.for_kind("not-a-real-kind")
    assert rules.sections["Outcome"].required is True


# ────────────────────────────────────────────────────────────────────
# Shipped YAML — content sanity (per-kind expectations match the spec)
# ────────────────────────────────────────────────────────────────────


def test_shipped_yaml_security_kind_demands_threat_model() -> None:
    cfg = load_gates_config()
    rules = cfg.definition_of_ready.for_kind("security")
    assert "Threat Model" in rules.sections
    assert rules.sections["Threat Model"].required is True


def test_shipped_yaml_chore_dor_is_lighter_than_feature() -> None:
    cfg = load_gates_config()
    feat = cfg.definition_of_ready.for_kind("feature")
    chore = cfg.definition_of_ready.for_kind("chore")
    # feature requires Acceptance; chore does not.
    assert feat.sections["Acceptance"].required is True
    assert "Acceptance" not in chore.sections or not chore.sections.get(
        "Acceptance",
    )


def test_shipped_yaml_bug_kind_requires_repro_steps() -> None:
    cfg = load_gates_config()
    rules = cfg.definition_of_ready.for_kind("bug")
    assert "Repro Steps" in rules.sections
    assert rules.sections["Repro Steps"].min_chars >= 20


def test_shipped_yaml_dod_docs_skips_verify() -> None:
    cfg = load_gates_config()
    docs_dod = cfg.definition_of_done.for_kind("docs")
    assert docs_dod.require_verify is False


def test_shipped_yaml_dod_default_requires_verify() -> None:
    cfg = load_gates_config()
    default_dod = cfg.definition_of_done.for_kind("feature")
    assert default_dod.require_verify is True
    assert default_dod.verify_max_age_seconds == 1800


# ────────────────────────────────────────────────────────────────────
# Override policy
# ────────────────────────────────────────────────────────────────────


def test_override_policy_demands_reason_by_default() -> None:
    pol = OverridePolicy()
    assert pol.require_reason is True
    assert pol.min_reason_chars == 15


def test_shipped_yaml_overrides_block_silent_bypass() -> None:
    cfg = load_gates_config()
    assert cfg.overrides.require_reason is True
    assert cfg.overrides.min_reason_chars >= 10


# ────────────────────────────────────────────────────────────────────
# Round-trip
# ────────────────────────────────────────────────────────────────────


def test_default_gates_yaml_round_trips() -> None:
    """yaml → model → dict round trips without losing per-kind structure."""
    cfg = load_gates_config()
    dumped = cfg.model_dump()
    rebuilt = GatesConfig.model_validate(dumped)
    assert rebuilt == cfg


def test_default_path_resolves_to_yaml_in_module_dir() -> None:
    assert DEFAULT_GATES_PATH.name == "transition-gates.yaml"
    assert DEFAULT_GATES_PATH.parent.name == "board_os"


# ────────────────────────────────────────────────────────────────────
# DoD verify-state contract (TASK-620) — freshness gate, defense-in-depth
# ────────────────────────────────────────────────────────────────────


def test_verify_state_contract(tmp_path, monkeypatch) -> None:
    # TASK-620: the DoD gate reads .last-verify.json for a recent PASS. It is a
    # freshness gate (not tree-bound, not forge-proof — same actor writes it), so
    # the contract is exactly: a recent PASS → (True, small age); no record →
    # (False, None); only a non-PASS entry → (False, None).
    import json
    import time

    from core.board_os import transition_gates_cli as cli

    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    path = tmp_path / ".last-verify.json"

    # no record at all → not satisfied
    assert cli._verify_state() == (False, None)

    # a recent PASS → satisfied, age is small and non-negative
    path.write_text(json.dumps({"cli": {"status": "PASS", "ts": int(time.time())}}), encoding="utf-8")
    ok, age = cli._verify_state()
    assert ok is True and age is not None and 0 <= age < 60

    # only a FAIL entry → not satisfied (a red run never unlocks the close)
    path.write_text(json.dumps({"cli": {"status": "FAIL", "ts": int(time.time())}}), encoding="utf-8")
    assert cli._verify_state() == (False, None)
