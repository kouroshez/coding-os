"""Tests for graph_os.toolchain (TASK-082).

Coverage matrix:
  - tsconfig.json paths + baseUrl + JSONC tolerance + extends
  - go.mod module prefix
  - Cargo.toml root + workspace members
  - pyproject.toml [tool.poetry.packages] / [project] name / setuptools
  - integration: code_ts._resolve_module_uid honours tsconfig aliases
  - integration: code_python._module_name_for_path honours pyproject
  - cache invalidation on mtime change
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from graph_os.toolchain import (
    ToolchainContext,
    get_active,
    load_toolchain,
    reset_cache,
    set_active,
)


@pytest.fixture(autouse=True)
def _clean_active():
    reset_cache()
    set_active(None)
    yield
    reset_cache()
    set_active(None)


# ---------------------------------------------------------------------------
# tsconfig.json
# ---------------------------------------------------------------------------


class TestTsconfig:
    def test_paths_extracted(self, tmp_path: Path):
        (tmp_path / "tsconfig.json").write_text(
            textwrap.dedent(
                """
                {
                  "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {
                      "@shared/*": ["packages/shared/src/*"],
                      "@app": ["src/app/index.ts"]
                    }
                  }
                }
                """
            ).strip()
        )
        ctx = load_toolchain(tmp_path)
        assert ctx.ts_paths["@shared/*"] == ("packages/shared/src/*",)
        assert ctx.ts_paths["@app"] == ("src/app/index.ts",)
        assert ctx.ts_base_url == ""  # "." resolves to repo root → empty

    def test_baseurl_subdir(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"baseUrl": "src"}}')
        ctx = load_toolchain(tmp_path)
        assert ctx.ts_base_url == "src"

    def test_jsonc_comments_tolerated(self, tmp_path: Path):
        (tmp_path / "tsconfig.json").write_text(
            textwrap.dedent(
                """
                // top-level comment
                {
                  /* block comment */
                  "compilerOptions": {
                    "paths": {
                      "@shared/*": ["packages/shared/*"], // trailing comma OK
                    }
                  },
                }
                """
            ).strip()
        )
        ctx = load_toolchain(tmp_path)
        assert "@shared/*" in ctx.ts_paths

    def test_malformed_tsconfig_returns_empty(self, tmp_path: Path):
        (tmp_path / "tsconfig.json").write_text("{ this is not json")
        ctx = load_toolchain(tmp_path)
        assert ctx.ts_paths == {}

    def test_no_tsconfig_empty_paths(self, tmp_path: Path):
        ctx = load_toolchain(tmp_path)
        assert ctx.ts_paths == {}
        assert ctx.ts_base_url == ""


# ---------------------------------------------------------------------------
# go.mod
# ---------------------------------------------------------------------------


class TestGoMod:
    def test_module_extracted(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module github.com/acme/myapp\n\ngo 1.22\n")
        ctx = load_toolchain(tmp_path)
        assert ctx.go_module == "github.com/acme/myapp"

    def test_no_go_mod(self, tmp_path: Path):
        ctx = load_toolchain(tmp_path)
        assert ctx.go_module == ""

    def test_module_with_trailing_slash_or_blank(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module   github.com/x/y\n")
        ctx = load_toolchain(tmp_path)
        assert ctx.go_module == "github.com/x/y"


# ---------------------------------------------------------------------------
# Cargo.toml
# ---------------------------------------------------------------------------


class TestCargo:
    def test_root_crate(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text(
            textwrap.dedent(
                """
                [package]
                name = "myapp"
                version = "0.1.0"
                """
            ).strip()
        )
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates == {"myapp": "."}

    def test_workspace_members(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text(
            textwrap.dedent(
                """
                [workspace]
                members = ["crates/core", "crates/api"]
                """
            ).strip()
        )
        for sub in ("crates/core", "crates/api"):
            (tmp_path / sub).mkdir(parents=True)
            (tmp_path / sub / "Cargo.toml").write_text(
                f'[package]\nname = "{sub.split("/")[-1]}"\nversion = "0.1.0"\n'
            )
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates["core"] == "crates/core"
        assert ctx.rust_crates["api"] == "crates/api"


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


class TestPyproject:
    def test_poetry_packages_with_from(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [tool.poetry]
                name = "myapp"

                [[tool.poetry.packages]]
                include = "myapp"
                from = "src"
                """
            ).strip()
        )
        (tmp_path / "src" / "myapp").mkdir(parents=True)
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages["myapp"] == "src/myapp"

    def test_project_name_src_layout(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [project]
                name = "myapp"
                """
            ).strip()
        )
        (tmp_path / "src" / "myapp").mkdir(parents=True)
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages["myapp"] == "src/myapp"

    def test_project_name_flat_layout(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "myapp").mkdir()
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages["myapp"] == "myapp"

    def test_no_pyproject_empty(self, tmp_path: Path):
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages == {}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestCache:
    def test_same_path_same_object(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module github.com/x/y\n")
        a = load_toolchain(tmp_path)
        b = load_toolchain(tmp_path)
        assert a is b

    def test_mtime_change_invalidates(self, tmp_path: Path):
        gomod = tmp_path / "go.mod"
        gomod.write_text("module a\n")
        a = load_toolchain(tmp_path)
        # Advance mtime via overwrite + os.utime
        import os

        gomod.write_text("module b\n")
        os.utime(gomod, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
        b = load_toolchain(tmp_path)
        assert b.go_module == "module b" or b.go_module == "b"
        assert a is not b


# ---------------------------------------------------------------------------
# Active context
# ---------------------------------------------------------------------------


class TestActive:
    def test_set_get_clear(self, tmp_path: Path):
        ctx = ToolchainContext(repo_root=str(tmp_path))
        assert get_active() is None
        set_active(ctx)
        assert get_active() is ctx
        set_active(None)
        assert get_active() is None


# ---------------------------------------------------------------------------
# TS extractor integration
# ---------------------------------------------------------------------------


class TestTsExtractorIntegration:
    def test_alias_resolves_to_repo_local(self, tmp_path: Path):
        from graph_os.extractors.code_ts import _resolve_module_uid

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"paths": {"@shared/*": ["packages/shared/src/*"]}}}'
        )
        set_active(load_toolchain(tmp_path))
        uid = _resolve_module_uid(
            origin="apps/web/src/login.ts",
            specifier="@shared/auth",
        )
        assert uid == "code:module:packages/shared/src/auth"

    def test_external_specifier_unchanged_without_alias(self, tmp_path: Path):
        from graph_os.extractors.code_ts import _resolve_module_uid

        set_active(load_toolchain(tmp_path))  # empty toolchain
        uid = _resolve_module_uid(
            origin="apps/web/src/login.ts",
            specifier="react",
        )
        assert uid == "code:module:npm:react"

    def test_relative_paths_unchanged(self, tmp_path: Path):
        from graph_os.extractors.code_ts import _resolve_module_uid

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"paths": {"@x/*": ["lib/*"]}}}'
        )
        set_active(load_toolchain(tmp_path))
        uid = _resolve_module_uid(
            origin="apps/web/src/login.ts",
            specifier="./helper",
        )
        assert uid == "code:module:apps/web/src/helper.ts"


# ---------------------------------------------------------------------------
# Python extractor integration
# ---------------------------------------------------------------------------


class TestPythonExtractorIntegration:
    def test_poetry_root_rebases_module_name(self, tmp_path: Path):
        from graph_os.extractors.code_python import _module_name_for_path

        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [[tool.poetry.packages]]
                include = "myapp"
                from = "packages"
                """
            ).strip()
        )
        (tmp_path / "packages" / "myapp").mkdir(parents=True)
        set_active(load_toolchain(tmp_path))
        # File at `packages/myapp/auth.py` becomes module `myapp.auth`
        assert _module_name_for_path("packages/myapp/auth.py") == "myapp.auth"

    def test_no_toolchain_falls_back_to_default(self, tmp_path: Path):
        from graph_os.extractors.code_python import _module_name_for_path

        set_active(None)
        # Default behavior: strip src/ prefix
        assert _module_name_for_path("src/myapp/auth.py") == "myapp.auth"
        # core/ prefix is also stripped
        assert _module_name_for_path("core/foo.py") == "foo"


# ---------------------------------------------------------------------------
# Error / edge branches (coverage of the defensive paths)
# ---------------------------------------------------------------------------


class TestGoModEdges:
    def test_go_mod_without_module_line_is_empty(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("go 1.22\nrequire x v1.0.0\n")
        ctx = load_toolchain(tmp_path)
        assert ctx.go_module == ""


class TestCargoEdges:
    def test_malformed_cargo_returns_empty(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text("[package\nname = broken")
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates == {}

    def test_workspace_member_without_cargo_toml_skipped(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text(
            '[workspace]\nmembers = ["crates/real", "crates/ghost"]\n'
        )
        (tmp_path / "crates" / "real").mkdir(parents=True)
        (tmp_path / "crates" / "real" / "Cargo.toml").write_text(
            '[package]\nname = "real"\nversion = "0.1.0"\n'
        )
        # crates/ghost has no Cargo.toml → silently skipped.
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates == {"real": "crates/real"}

    def test_workspace_member_malformed_cargo_skipped(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["m"]\n')
        (tmp_path / "m").mkdir()
        (tmp_path / "m" / "Cargo.toml").write_text("[package broken")
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates == {}


class TestPyprojectEdges:
    def test_malformed_pyproject_returns_empty(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project\nname = broken")
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages == {}

    def test_setuptools_package_dir(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [tool.setuptools]
                package-dir = {mypkg = "lib/mypkg"}
                """
            ).strip()
        )
        (tmp_path / "lib" / "mypkg").mkdir(parents=True)
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages["mypkg"] == "lib/mypkg"

    def test_poetry_include_without_from(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [[tool.poetry.packages]]
                include = "flatpkg"
                """
            ).strip()
        )
        (tmp_path / "flatpkg").mkdir()
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages["flatpkg"] == "flatpkg"

    def test_project_name_no_matching_dir_omitted(self, tmp_path: Path):
        # [project] name present but neither src/<name> nor <name> exists.
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "ghost"\n')
        ctx = load_toolchain(tmp_path)
        assert "ghost" not in ctx.python_packages

    def test_cargo_package_without_name_no_root_crate(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text('[package]\nversion = "0.1.0"\n')
        ctx = load_toolchain(tmp_path)
        assert ctx.rust_crates == {}

    def test_poetry_entry_missing_include_skipped(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [[tool.poetry.packages]]
                from = "src"
                """
            ).strip()
        )
        ctx = load_toolchain(tmp_path)
        assert ctx.python_packages == {}

    def test_setuptools_package_dir_missing_dir_omitted(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.setuptools]\npackage-dir = {gone = "nope/gone"}\n'
        )
        ctx = load_toolchain(tmp_path)
        assert "gone" not in ctx.python_packages
