"""Polyglot extractor corpus — scripting and web languages.

Per-language source snippets the extractor quality tests measure recall
and precision against. Data, not logic: each language entry changes alone.
"""

from __future__ import annotations

from graph_os.extractors import (
    code_generic,
    code_php,
    code_python,
    code_shell,
    code_ts,
)
from graph_os.tests.polyglot_scenario import Scenario

CORPUS: dict[str, tuple[object, list[Scenario]]] = {
    "ruby": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.rb",
                'require "set"\ndef helper; 1; end\ndef main; helper; end\nclass Point; end\n',
                funcs={"helper", "main"},
                classes={"Point"},
                edges=[
                    ("imports", "s1.rb", "set"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.rb",
                "module Geometry\n"
                "  class Shape\n"
                "    def area; 0; end\n"
                "    def self.build; new; end\n"
                "  end\n"
                "end\n"
                "class Circle < Shape\n  include Comparable\nend\n",
                funcs={"area", "build"},
                classes={"Geometry", "Shape", "Circle"},
                edges=[
                    ("inherits", "Circle", "Shape"),
                    ("includes", "Circle", "Comparable"),
                ],
            ),
            Scenario(
                "realworld",
                "s3.rb",
                'require_relative "config"\n'
                "# def decoy; end — commented out\n"
                "class Service\n"
                "  def run\n"
                '    msg = "def fake_fn; end"\n'
                "    validate\n"
                "    client.fetch\n"
                "  end\n"
                "  def validate; true; end\n"
                "end\n",
                funcs={"run", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.rb", "config"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ------------------------------------------------------------------ java
    "lua": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.lua",
                'local m = require("mod")\n'
                "function helper() return 1 end\n"
                "function main() helper() end\n",
                funcs={"helper", "main"},
                edges=[
                    ("imports", "s1.lua", "mod"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.lua",
                "local function validate() return true end\nfunction run()\n  validate()\nend\n",
                funcs={"validate", "run"},
                edges=[("calls", "::run", "::validate")],
            ),
            Scenario(
                "realworld",
                "s3.lua",
                'local cfg = require("config")\n'
                "-- function decoy() end — commented out\n"
                "function run()\n"
                '  local msg = "function fake_fn() end"\n'
                "  validate()\n"
                "  client.fetch()\n"
                "end\n"
                "function validate() return true end\n",
                funcs={"run", "validate"},
                edges=[
                    ("imports", "s3.lua", "config"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ---------------------------------------------------------------- python
    "python": (
        code_python,
        [
            Scenario(
                "simple",
                "s1.py",
                "import os\n"
                "def helper():\n    return 1\n"
                "def main():\n    helper()\n"
                "class Point:\n    pass\n",
                funcs={"helper", "main"},
                classes={"Point"},
                edges=[
                    # code_python import edges link module uids (code:module:s1)
                    ("imports", "module:s1", "os"),
                    ("calls", "main", "helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.py",
                "class Shape:\n"
                "    def draw(self):\n        pass\n"
                "    class Inner:\n        def poke(self):\n            pass\n"
                "class Circle(Shape):\n"
                "    def area(self):\n        return 0\n",
                funcs={"draw", "poke", "area"},
                classes={"Shape", "Inner", "Circle"},
                edges=[("inherits_from", "Circle", "Shape")],
            ),
            Scenario(
                "realworld",
                "s3.py",
                "from typing import Any\n"
                "# def decoy(): pass — commented out\n"
                "class Service:\n"
                "    def run(self):\n"
                "        msg = 'def fake_fn(): pass'\n"
                "        self.validate()\n"
                "        validate_input()\n"
                "    def validate(self):\n        return True\n"
                "def validate_input():\n    return True\n",
                funcs={"run", "validate", "validate_input"},
                classes={"Service"},
                edges=[
                    ("imports", "module:s3", "typing"),
                    ("calls", "run", "validate_input"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # -------------------------------------------------------------------- go
    "typescript": (
        code_ts,
        [
            Scenario(
                "simple",
                "s1.ts",
                'import { x } from "./x";\n'
                "export function helper(): number { return 1; }\n"
                "export function main(): void { helper(); }\n"
                "export class Point {}\n",
                funcs={"helper", "main"},
                classes={"Point"},
                edges=[
                    # code_ts import edges link module uids (code:module:x.ts)
                    ("imports", "s1.ts", "module:x"),
                    ("calls", "main", "helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.ts",
                "interface Render { draw(): void; }\n"
                "export class Shape implements Render {\n"
                "  draw(): void {}\n"
                "}\n"
                "export class Circle extends Shape {\n"
                "  area(): number { return 0; }\n"
                "}\n",
                funcs={"draw", "area"},
                classes={"Render", "Shape", "Circle"},
                edges=[],
            ),
            Scenario(
                "realworld",
                "s3.ts",
                'import { api } from "./api";\n'
                "// function decoy() {} — commented out\n"
                "export class Service {\n"
                "  run(): void {\n"
                '    const msg = "function fake_fn() {}";\n'
                "    validateInput();\n"
                "  }\n"
                "}\n"
                "function validateInput(): boolean { return true; }\n",
                funcs={"run", "validateInput"},
                classes={"Service"},
                edges=[("imports", "s3.ts", "module:api")],
                has_decoys=True,
            ),
        ],
    ),
    # ------------------------------------------------------------------- php
    "php": (
        code_php,
        [
            Scenario(
                "simple",
                "s1.php",
                "<?php\n"
                "function helper(): int { return 1; }\n"
                "function main(): void { helper(); }\n"
                "class Point {}\n",
                funcs={"helper", "main"},
                classes={"Point"},
                edges=[("calls", "main", "helper")],
            ),
            Scenario(
                "nested",
                "s2.php",
                "<?php\n"
                "interface Render { public function draw(): void; }\n"
                "trait Loggable { public function log(): void {} }\n"
                "class Shape implements Render {\n"
                "  public function draw(): void {}\n"
                "}\n"
                "class Circle extends Shape {\n"
                "  public function area(): float { return 0.0; }\n"
                "}\n",
                funcs={"draw", "log", "area"},
                classes={"Render", "Loggable", "Shape", "Circle"},
                edges=[("inherits_from", "Circle", "Shape")],
            ),
            Scenario(
                "realworld",
                "s3.php",
                "<?php\n"
                "// function decoy() {} — commented out\n"
                "class Service extends Base {\n"
                "  public function run(): void {\n"
                "    $msg = 'function fake_fn() {}';\n"
                "    $this->validate();\n"
                "    validateInput();\n"
                "  }\n"
                "  public function validate(): bool { return true; }\n"
                "}\n"
                "function validateInput(): bool { return true; }\n",
                funcs={"run", "validate", "validateInput"},
                classes={"Service"},
                edges=[("inherits_from", "Service", "Base")],
                has_decoys=True,
            ),
        ],
    ),
    # ----------------------------------------------------------------- shell
    "shell": (
        code_shell,
        [
            Scenario(
                "simple",
                "s1.sh",
                "source ./env.sh\nhelper() { echo hi; }\nmain() { helper; }\n",
                funcs={"helper", "main"},
                edges=[
                    ("imports", "s1.sh", "env.sh"),
                    ("calls", "main", "helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.sh",
                "validate() { return 0; }\n"
                "run() {\n  validate\n  set -e\n}\n"
                "cleanup() { rm -f /tmp/x; }\n",
                funcs={"validate", "run", "cleanup"},
                edges=[("calls", "run", "validate")],
            ),
            Scenario(
                "realworld",
                "s3.sh",
                "#!/usr/bin/env bash\n"
                "# decoy() { echo no; } — commented out\n"
                "run() {\n"
                "  cat <<'EOF'\n"
                "fake_fn() { echo decoy-in-heredoc; }\n"
                "EOF\n"
                "  validate\n"
                "}\n"
                "validate() { return 0; }\n",
                funcs={"run", "validate"},
                edges=[("calls", "run", "validate")],
                has_decoys=True,
            ),
        ],
    ),
}
