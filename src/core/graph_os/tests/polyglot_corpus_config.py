"""Polyglot extractor corpus — configuration and manifest formats."""

from __future__ import annotations

from graph_os.extractors import (
    code_json,
    code_toml,
    code_yaml,
)
from graph_os.tests.polyglot_scenario import Scenario

CONFIG_CORPUS: dict[str, tuple[object, list[Scenario]]] = {
    "yaml": (
        code_yaml,
        [
            Scenario(
                "gha-workflow",
                "wf.yaml",
                "name: ci\non: push\njobs:\n  test:\n    runs-on: ubuntu\n"
                "    steps:\n      - run: make test\n",
                # `on=push` pins the YAML-1.1 bool-key fix — safe_load used to
                # mangle this hottest GitHub Actions key into `True=push`.
                funcs={
                    "name=ci",
                    "on=push",
                    "jobs=dict",
                    "test=dict",
                    "runs-on=ubuntu",
                    "steps=list",
                    "run=make test",
                },
            ),
            Scenario(
                "compose",
                "docker-compose.yml",
                "services:\n  api:\n    image: app:1\n    ports:\n      - 8080:8080\n"
                "  db:\n    image: postgres:16\n",
                funcs={
                    "services=dict",
                    "api=dict",
                    "db=dict",
                    "image=app:1",
                    "image=postgres:16",
                    "ports=list",
                },
            ),
        ],
    ),
    "json": (
        code_json,
        [
            Scenario(
                "package-json",
                "package.json",
                '{"name":"app","dependencies":{"react":"18"},'
                '"devDependencies":{"vitest":"2"},'
                '"scripts":{"build":"tsc","test":"vitest"}}',
                funcs={
                    "app",
                    "npm:package:react",
                    "npm:package:vitest",
                    "npm:build",
                    "npm:test",
                },
            ),
            Scenario(
                "tsconfig",
                "tsconfig.json",
                '{"compilerOptions":{"paths":{"@app/*":["src/*"]}}}',
                funcs={"@app/*"},
            ),
        ],
    ),
    "toml": (
        code_toml,
        [
            Scenario(
                "pyproject",
                "pyproject.toml",
                '[project]\nname = "app"\ndependencies = ["click>=8", "pyyaml"]\n',
                funcs={"app", "pypi:package:click", "pypi:package:pyyaml"},
            ),
            Scenario(
                "cargo",
                "Cargo.toml",
                '[package]\nname = "svc"\n[dependencies]\nserde = "1"\n'
                'tokio = { version = "1", features = ["full"] }\n',
                funcs={"svc", "crates:package:serde", "crates:package:tokio"},
            ),
        ],
    ),
}
