"""graph_os — TOML extractor.

Targets: pyproject.toml, Cargo.toml, generic .toml configs. Emits package
dependencies, workspace members, scripts/binaries, and tool tables.

Spec: docs/playbooks/polyglot-extractor-roadmap.md §4.7 (Epic B2).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_toml")
EXTRACTOR_ID = "code_toml@v1"

try:
    import tomllib  # 3.11+

    _TOML_ERR = tomllib.TOMLDecodeError
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]

        _TOML_ERR = tomllib.TOMLDecodeError
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]
        _TOML_ERR = ValueError  # type: ignore[assignment]


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def _config_uid(path: str, pointer: str) -> str:
    return f"config:toml:{_normalize_path(path)}#{pointer}"


def _emit_pyproject(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    project = data.get("project") or {}
    if isinstance(project, dict):
        name = project.get("name")
        if isinstance(name, str) and name:
            pkg_uid = f"pypi:package:{name}"
            result.nodes.append(
                GraphNode(
                    uid=pkg_uid,
                    kind="contract",
                    label=name,
                    file_path=normalised,
                    lang="toml",
                    metadata={"extractor": EXTRACTOR_ID, "subkind": "pypi_package"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=pkg_uid,
                    edge_type="declares",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
        # E9: emit deps from main + optional-dependencies (PEP 621) +
        # dependency-groups (PEP 735). Was only walking main deps.
        def _emit_dep_list(dep_list: Any, evidence_name: str) -> None:
            if not isinstance(dep_list, list):
                return
            for entry in dep_list:
                if not isinstance(entry, str):
                    continue
                dep_name = (
                    entry.split(";")[0]
                    .strip()
                    .split()[0]
                    .split("[")[0]
                    .split("==")[0]
                    .split(">=")[0]
                    .split("<=")[0]
                    .split("!=")[0]
                    .split("~=")[0]
                    .split(">")[0]
                    .split("<")[0]
                    .strip()
                )
                if dep_name:
                    result.edges.append(
                        GraphEdge(
                            source_uid=file_uid_,
                            target_uid=f"pypi:package:{dep_name}",
                            edge_type="imports",
                            extractor=EXTRACTOR_ID,
                            confidence=0.9,
                            evidence=(EvidenceSignal(evidence_name, 0.9),),
                        )
                    )

        _emit_dep_list(project.get("dependencies"), "pyproject_dependency")
        # PEP 621 optional-dependencies — {"rag": [...], "graph_os": [...], ...}
        optional_deps = project.get("optional-dependencies") or {}
        if isinstance(optional_deps, dict):
            for group_name, group_deps in optional_deps.items():
                _emit_dep_list(group_deps, f"pyproject_optional_{group_name}")
        # PEP 735 dependency-groups (top-level, not under project).
        dep_groups = data.get("dependency-groups") or {}
        if isinstance(dep_groups, dict):
            for group_name, group_deps in dep_groups.items():
                _emit_dep_list(group_deps, f"pep735_group_{group_name}")
        scripts = project.get("scripts")
        if isinstance(scripts, dict):
            for script_name in scripts.keys():
                if not isinstance(script_name, str):
                    continue
                uid = _config_uid(path, f"/project/scripts/{script_name}")
                result.nodes.append(
                    GraphNode(
                        uid=uid,
                        kind="tool",
                        label=script_name,
                        file_path=normalised,
                        lang="toml",
                        metadata={"extractor": EXTRACTOR_ID, "subkind": "pyproject_script"},
                    )
                )
                result.edges.append(
                    GraphEdge(
                        source_uid=file_uid_,
                        target_uid=uid,
                        edge_type="contains",
                        extractor=EXTRACTOR_ID,
                        confidence=1.0,
                    )
                )


def _emit_cargo(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    pkg = data.get("package") or {}
    if isinstance(pkg, dict):
        name = pkg.get("name")
        if isinstance(name, str) and name:
            crate_uid = f"crates:package:{name}"
            result.nodes.append(
                GraphNode(
                    uid=crate_uid,
                    kind="contract",
                    label=name,
                    file_path=normalised,
                    lang="toml",
                    metadata={"extractor": EXTRACTOR_ID, "subkind": "crate"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=crate_uid,
                    edge_type="declares",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
    for dep_section in ("dependencies", "dev-dependencies", "build-dependencies"):
        deps = data.get(dep_section)
        if not isinstance(deps, dict):
            continue
        for crate_name in deps.keys():
            if not isinstance(crate_name, str):
                continue
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=f"crates:package:{crate_name}",
                    edge_type="imports",
                    extractor=EXTRACTOR_ID,
                    confidence=0.95,
                    evidence=(EvidenceSignal(dep_section, 0.95),),
                )
            )
    workspace = data.get("workspace") or {}
    if isinstance(workspace, dict):
        members = workspace.get("members")
        if isinstance(members, list):
            origin_dir = PurePosixPath(normalised).parent
            for member in members:
                if not isinstance(member, str):
                    continue
                # Glob patterns (e.g. "crates/*") emit a folder edge to the
                # parent dir; concrete paths emit a direct member edge.
                stripped = member.rstrip("/*")
                resolved = (origin_dir / stripped).as_posix() if stripped else origin_dir.as_posix()
                result.edges.append(
                    GraphEdge(
                        source_uid=file_uid_,
                        target_uid=f"folder:{resolved}",
                        edge_type="contains",
                        extractor=EXTRACTOR_ID,
                        confidence=0.8,
                        evidence=(EvidenceSignal("cargo_workspace_member", 0.8),),
                    )
                )


def _detect_subtype(name: str) -> str:
    lname = name.lower()
    if lname == "pyproject.toml":
        return "pyproject"
    if lname == "cargo.toml":
        return "cargo"
    return "generic"


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a TOML config file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    file_name = PurePosixPath(normalised).name
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=file_name,
        file_path=normalised,
        lang="toml",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    if tomllib is None:
        result.parse_errors.append(
            ParseError(
                kind="missing_dep",
                detail="tomllib unavailable (Python < 3.11 and tomli not installed)",
            )
        )
        emit_contains_spine(
            file_path=path,
            file_uid_=file_uid(path),
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    try:
        data = tomllib.loads(content)
    except _TOML_ERR as exc:
        result.parse_errors.append(ParseError(kind="toml_decode", detail=str(exc)))
        emit_contains_spine(
            file_path=path,
            file_uid_=file_uid(path),
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    subtype = _detect_subtype(file_name)
    if isinstance(data, dict):
        if subtype == "pyproject":
            _emit_pyproject(data, path, normalised, file_node.uid, result)
        elif subtype == "cargo":
            _emit_cargo(data, path, normalised, file_node.uid, result)

    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid(path),
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    _promote_stubs(result)
    return result


__all__ = ["EXTRACTOR_ID", "extract", "file_uid"]
