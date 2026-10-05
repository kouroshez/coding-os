"""Import-specifier resolution for TypeScript / JavaScript (graph_os.resolve_ts)."""

from __future__ import annotations

import json
from pathlib import Path

from graph_os.resolve_ts import alias_target, resolve


def _touch(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(root: Path, relative: str, data: dict) -> None:
    _touch(root, relative, json.dumps(data))


class TestRelative:
    def test_esm_js_suffix_resolves_to_the_ts_source(self, tmp_path):
        _touch(tmp_path, "src/utils/helper.ts")
        assert resolve("src/app.ts", "./utils/helper.js", tmp_path) == "src/utils/helper.ts"

    def test_extensionless_import_finds_a_tsx_component(self, tmp_path):
        _touch(tmp_path, "src/Button.tsx")
        assert resolve("src/App.tsx", "./Button", tmp_path) == "src/Button.tsx"

    def test_directory_import_finds_its_index(self, tmp_path):
        _touch(tmp_path, "src/components/index.ts")
        assert resolve("src/App.tsx", "./components", tmp_path) == "src/components/index.ts"

    def test_react_native_platform_variant(self, tmp_path):
        _touch(tmp_path, "src/Card.ios.tsx")
        assert resolve("src/App.tsx", "./Card", tmp_path) == "src/Card.ios.tsx"

    def test_missing_file_is_unresolved(self, tmp_path):
        assert resolve("src/App.tsx", "./Nowhere", tmp_path) is None

    def test_path_escaping_the_repo_is_unresolved(self, tmp_path):
        assert resolve("a.ts", "../../outside", tmp_path) is None


class TestTsconfigPaths:
    def test_nearest_tsconfig_alias_through_extends(self, tmp_path):
        _touch(
            tmp_path,
            "tsconfig.base.json",
            '{\n  "$schema": "https://json.schemastore.org/tsconfig",\n'
            '  // shared options\n  "compilerOptions": {"strict": true,},\n}\n',
        )
        _json(
            tmp_path,
            "apps/console/tsconfig.json",
            {
                "extends": "../../tsconfig.base.json",
                "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}},
            },
        )
        _touch(tmp_path, "apps/console/src/lib/fetchers.ts")

        resolved = resolve("apps/console/src/pages/Home.tsx", "@/lib/fetchers", tmp_path)

        assert resolved == "apps/console/src/lib/fetchers.ts"

    def test_paths_inherited_without_base_url_resolve_from_their_own_config(self, tmp_path):
        _json(tmp_path, "tsconfig.json", {"compilerOptions": {"paths": {"~/*": ["./lib/*"]}}})
        _json(tmp_path, "web/tsconfig.json", {"extends": "../tsconfig.json"})
        _touch(tmp_path, "lib/date.ts")
        assert resolve("web/src/page.ts", "~/date", tmp_path) == "lib/date.ts"

    def test_bare_package_is_not_mistaken_for_a_base_url_file(self, tmp_path):
        _json(tmp_path, "tsconfig.json", {"compilerOptions": {"baseUrl": "src"}})
        assert resolve("src/app.ts", "react", tmp_path) is None

    def test_alias_target_names_a_missing_file(self, tmp_path):
        _json(tmp_path, "tsconfig.json", {"compilerOptions": {"paths": {"@/*": ["./src/*"]}}})
        assert alias_target("src/app.ts", "@/gone", tmp_path) == "src/gone"


class TestWorkspacePackages:
    def test_pnpm_package_exports_entry_and_subpath(self, tmp_path):
        _touch(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n  - 'apps/web'\n")
        _json(
            tmp_path,
            "packages/ui/package.json",
            {
                "name": "@acme/ui",
                "exports": {".": "./src/index.ts", "./theme": "./src/theme.ts"},
            },
        )
        _touch(tmp_path, "packages/ui/src/index.ts")
        _touch(tmp_path, "packages/ui/src/theme.ts")

        assert resolve("apps/web/page.tsx", "@acme/ui", tmp_path) == "packages/ui/src/index.ts"
        assert resolve("apps/web/page.tsx", "@acme/ui/theme", tmp_path) == (
            "packages/ui/src/theme.ts"
        )

    def test_npm_workspaces_field_and_main_entry(self, tmp_path):
        _json(tmp_path, "package.json", {"workspaces": {"packages": ["libs/*"]}})
        _json(tmp_path, "libs/core/package.json", {"name": "core-lib", "main": "lib/index.js"})
        _touch(tmp_path, "libs/core/lib/index.ts")
        assert resolve("app/main.ts", "core-lib", tmp_path) == "libs/core/lib/index.ts"

    def test_conditional_exports_prefer_types(self, tmp_path):
        _json(tmp_path, "package.json", {"workspaces": ["pkgs/*"]})
        _json(
            tmp_path,
            "pkgs/log/package.json",
            {
                "name": "log",
                "exports": {".": {"types": "./src/log.ts", "default": "./dist/log.js"}},
            },
        )
        _touch(tmp_path, "pkgs/log/src/log.ts")
        assert resolve("app/main.ts", "log", tmp_path) == "pkgs/log/src/log.ts"

    def test_third_party_package_stays_external(self, tmp_path):
        _touch(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
        assert resolve("apps/web/page.tsx", "react-native", tmp_path) is None
