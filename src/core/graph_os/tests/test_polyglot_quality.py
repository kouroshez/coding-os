"""Polyglot quality benchmark — measured, not judged (TASK-313).

Ground-truth corpora per language × 3 scenarios (personas):
  S1 simple    — junior-dev file: flat functions, one class, imports.
  S2 nested    — library author: methods in classes, nesting, inheritance.
  S3 realworld — enterprise service file: mixed imports, same-file +
                 cross-file + dynamic calls, inheritance, and DECOY code
                 inside comments/strings that must NOT be extracted.

Measured axes (the enterprise scorecard):
  coverage  = symbol recall (every human-visible function/class extracted)
              + edge recall (expected imports/calls/inherits found)
  accuracy  = precision in the function/class buckets (no phantoms) and
              zero decoy leakage
  trust     = confidence calibration: every calls edge at conf ≥ 0.9 must
              resolve to a real same-file uid (never an external guess)
  speed     = median extract() ms per file
  resources = peak tracemalloc bytes per extract

Thresholds (asserted — a miss is a red test, not a footnote):
  symbol recall ≥ 0.90 · precision ≥ 0.95 · edge recall ≥ 0.80
  median ≤ 25 ms/file · peak ≤ 6 MB/file

Run `python -m pytest <this file> -q` for the gate, or
`python src/core/graph_os/tests/test_polyglot_quality.py` for the
per-language stats table used in the score report.
"""

from __future__ import annotations

import statistics
import time
import tracemalloc
from dataclasses import dataclass, field

import pytest

pytest.importorskip("tree_sitter")

from graph_os.extractors import (  # noqa: E402
    code_generic,
    code_go,
    code_json,
    code_php,
    code_python,
    code_shell,
    code_toml,
    code_ts,
    code_yaml,
)

_FUNC_KINDS = {"code:function", "code:method"}
_CLASS_KINDS = {"code:class", "code:interface", "code:trait", "code:struct", "code:enum"}
_DECOY_NAMES = {"decoy", "fake_fn", "FakeClass", "phantom"}


@dataclass
class Scenario:
    name: str
    file: str
    src: str
    funcs: set[str]
    classes: set[str] = field(default_factory=set)
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (type, src_frag, tgt_frag)
    has_decoys: bool = False


def _last_segment(label: str) -> str:
    for sep in ("::", "."):
        if sep in label:
            label = label.rsplit(sep, 1)[-1]
    return label


def _extracted_names(result, kinds: set[str]) -> set[str]:
    return {_last_segment(n.label) for n in result.nodes if n.kind in kinds and n.label}


CORPUS: dict[str, tuple[object, list[Scenario]]] = {
    # ------------------------------------------------------------------ rust
    "rust": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.rs",
                "use std::fmt;\n"
                "struct Point { x: i32 }\n"
                "fn helper() -> i32 { 1 }\n"
                "fn main() { helper(); }\n",
                funcs={"helper", "main"},
                classes={"Point"},
                edges=[
                    ("imports", "s1.rs", "std::fmt"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.rs",
                "trait Render { fn draw(&self); }\n"
                "enum Shape { Circle, Square }\n"
                "mod geometry {\n    pub fn area() -> f64 { 0.0 }\n}\n"
                "impl Render for Shape { fn draw(&self) {} }\n",
                funcs={"draw", "area"},
                classes={"Render", "Shape", "geometry"},
                edges=[("implements", "Shape", "Render")],
            ),
            Scenario(
                "realworld",
                "s3.rs",
                "use serde::Serialize;\n"
                "use std::collections::HashMap;\n"
                "// fn decoy() {} — commented out\n"
                "struct Service { cache: HashMap<String, String> }\n"
                "fn build() -> Service { validate(); remote::fetch(); Service { cache: HashMap::new() } }\n"
                'fn validate() { let _msg = "fn fake_fn() {}"; }\n',
                funcs={"build", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.rs", "serde"),
                    ("calls", "::build", "::validate"),
                    ("calls", "::build", "external:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ------------------------------------------------------------------ ruby
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
    "java": (
        code_generic,
        [
            Scenario(
                "simple",
                "S1.java",
                "import java.util.List;\n"
                "class App {\n"
                "  void main() { helper(); }\n"
                "  int helper() { return 1; }\n"
                "}\n",
                funcs={"main", "helper"},
                classes={"App"},
                edges=[
                    ("imports", "S1.java", "java.util.List"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "S2.java",
                "interface Render { void draw(); }\n"
                "enum Color { RED }\n"
                "class Shape implements Render {\n"
                "  public void draw() {}\n"
                "  static class Inner { void poke() {} }\n"
                "}\n"
                "class Circle extends Shape {}\n",
                funcs={"draw", "poke"},
                classes={"Render", "Color", "Shape", "Inner", "Circle"},
                edges=[
                    ("implements", "Shape", "Render"),
                    ("inherits", "Circle", "Shape"),
                ],
            ),
            Scenario(
                "realworld",
                "S3.java",
                "import java.io.IOException;\n"
                "import java.util.Map;\n"
                "// void decoy() {} — commented out\n"
                "class Service extends Base {\n"
                "  void run() {\n"
                '    String s = "void fake_fn() {}";\n'
                "    validate();\n"
                "    client.fetch();\n"
                "  }\n"
                "  boolean validate() { return true; }\n"
                "}\n",
                funcs={"run", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "S3.java", "java.io.IOException"),
                    ("inherits", "Service", "Base"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # --------------------------------------------------------------------- c
    "c": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.c",
                "#include <stdio.h>\n"
                "int helper(void) { return 1; }\n"
                "int main(void) { helper(); return 0; }\n",
                funcs={"helper", "main"},
                edges=[
                    ("imports", "s1.c", "stdio.h"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.c",
                "struct point { int x; };\n"
                "enum color { RED };\n"
                "union value { int i; };\n"
                "static void draw(struct point *p) {}\n"
                "void render(void) { draw(0); }\n",
                funcs={"draw", "render"},
                classes={"point", "color", "value"},
                edges=[("calls", "::render", "::draw")],
            ),
            Scenario(
                "realworld",
                "s3.c",
                "#include <stdlib.h>\n"
                '#include "service.h"\n'
                "/* void decoy(void) {} — commented out */\n"
                "struct service { int id; };\n"
                "int validate(void) { return 1; }\n"
                "int run(struct service *s) {\n"
                '  const char *msg = "void fake_fn(void) {}";\n'
                "  validate();\n"
                "  s->fetch();\n"
                "  return 0;\n"
                "}\n",
                funcs={"validate", "run"},
                classes={"service"},
                edges=[
                    ("imports", "s3.c", "service.h"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ------------------------------------------------------------------- cpp
    "cpp": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.cpp",
                "#include <vector>\n"
                "int helper() { return 1; }\n"
                "int main() { helper(); return 0; }\n",
                funcs={"helper", "main"},
                edges=[
                    ("imports", "s1.cpp", "vector"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.cpp",
                "class Shape {\n public:\n  virtual void draw() {}\n};\n"
                "class Circle : public Shape {\n public:\n  void draw() {}\n};\n"
                "struct Pair { int a; };\n",
                funcs={"draw"},
                classes={"Shape", "Circle", "Pair"},
                edges=[("inherits", "Circle", "Shape")],
            ),
            Scenario(
                "realworld",
                "s3.cpp",
                "#include <string>\n"
                "// void decoy() {} — commented out\n"
                "class Service : public Base {\n"
                " public:\n"
                "  void run() {\n"
                '    std::string s = "void fake_fn() {}";\n'
                "    validate();\n"
                "    client->fetch();\n"
                "  }\n"
                "  bool validate() { return true; }\n"
                "};\n",
                funcs={"run", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.cpp", "string"),
                    ("inherits", "Service", "Base"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # --------------------------------------------------------------- c_sharp
    "c_sharp": (
        code_generic,
        [
            Scenario(
                "simple",
                "S1.cs",
                "using System;\n"
                "class App {\n"
                "  void Main() { Helper(); }\n"
                "  int Helper() { return 1; }\n"
                "}\n",
                funcs={"Main", "Helper"},
                classes={"App"},
                edges=[
                    ("imports", "S1.cs", "System"),
                    ("calls", "::Main", "::Helper"),
                ],
            ),
            Scenario(
                "nested",
                "S2.cs",
                "interface IRender { void Draw(); }\n"
                "struct Pair { public int A; }\n"
                "class Shape : IRender {\n"
                "  public void Draw() {}\n"
                "  class Inner { void Poke() {} }\n"
                "}\n",
                funcs={"Draw", "Poke"},
                classes={"IRender", "Pair", "Shape", "Inner"},
                edges=[("inherits", "Shape", "IRender")],
            ),
            Scenario(
                "realworld",
                "S3.cs",
                "using System.Collections.Generic;\n"
                "// void Decoy() {} — commented out\n"
                "class Service : Base {\n"
                "  void Run() {\n"
                '    var s = "void fake_fn() {}";\n'
                "    Validate();\n"
                "    client.Fetch();\n"
                "  }\n"
                "  bool Validate() { return true; }\n"
                "}\n",
                funcs={"Run", "Validate"},
                classes={"Service"},
                edges=[
                    ("imports", "S3.cs", "System.Collections.Generic"),
                    ("inherits", "Service", "Base"),
                    ("calls", "::Run", "::Validate"),
                    ("calls", "::Run", "unresolved:Fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ----------------------------------------------------------------- scala
    "scala": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.scala",
                "import scala.util.Try\n"
                "class App {\n"
                "  def main(): Unit = { helper() }\n"
                "  def helper(): Int = 1\n"
                "}\n",
                funcs={"main", "helper"},
                classes={"App"},
                edges=[
                    ("imports", "s1.scala", "scala.util.Try"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.scala",
                "trait Render { def draw(): Unit }\n"
                "object Registry { def lookup(): Int = 1 }\n"
                "class Shape extends Render { def draw(): Unit = {} }\n"
                "class Circle extends Shape with Render { def area(): Double = 0.0 }\n",
                funcs={"draw", "lookup", "area"},
                classes={"Render", "Registry", "Shape", "Circle"},
                edges=[
                    ("inherits", "Shape", "Render"),
                    ("inherits", "Circle", "Shape"),
                    ("includes", "Circle", "Render"),
                ],
            ),
            Scenario(
                "realworld",
                "s3.scala",
                "import java.time.Instant\n"
                "// def decoy(): Unit = {} — commented out\n"
                "class Service extends Base {\n"
                "  def run(): Unit = {\n"
                '    val s = "def fake_fn(): Unit = {}"\n'
                "    validate()\n"
                "    client.fetch()\n"
                "  }\n"
                "  def validate(): Boolean = true\n"
                "}\n",
                funcs={"run", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.scala", "java.time.Instant"),
                    ("inherits", "Service", "Base"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ---------------------------------------------------------------- kotlin
    "kotlin": (
        code_generic,
        [
            Scenario(
                "simple",
                "s1.kt",
                "import kotlin.math.abs\n"
                "class App {\n"
                "  fun main() { helper() }\n"
                "  fun helper(): Int = 1\n"
                "}\n",
                funcs={"main", "helper"},
                classes={"App"},
                edges=[
                    ("imports", "s1.kt", "kotlin.math.abs"),
                    ("calls", "::main", "::helper"),
                ],
            ),
            Scenario(
                # NOTE: multiline class bodies on purpose — tree-sitter-kotlin
                # 1.1.0 mis-parses a SINGLE-LINE class body with members when
                # it follows another declaration (`class A { fun x() {} }\n
                # class B { fun y() {} }` → ERROR). Multiline is also the real
                # Kotlin style. The quirk is pinned in
                # test_kotlin_grammar_quirk_is_surfaced (visible, fail-open).
                "nested",
                "s2.kt",
                "object Registry {\n  fun lookup(): Int {\n    return 1\n  }\n}\n"
                "class Shape {\n  fun draw() {}\n  class Inner {\n    fun poke() {}\n  }\n}\n"
                "class Circle : Shape() {\n  fun area(): Double {\n    return 0.0\n  }\n}\n",
                funcs={"lookup", "draw", "poke", "area"},
                classes={"Registry", "Shape", "Inner", "Circle"},
                edges=[("inherits", "Circle", "Shape")],
            ),
            Scenario(
                "realworld",
                "s3.kt",
                "import java.time.Instant\n"
                "// fun decoy() {} — commented out\n"
                "class Service : Base(), Runnable {\n"
                "  fun run() {\n"
                '    val s = "fun fake_fn() {}"\n'
                "    validate()\n"
                "    client.fetch()\n"
                "  }\n"
                "  fun validate(): Boolean = true\n"
                "}\n",
                funcs={"run", "validate"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.kt", "java.time.Instant"),
                    ("inherits", "Service", "Base"),
                    ("implements", "Service", "Runnable"),
                    ("calls", "::run", "::validate"),
                    ("calls", "::run", "unresolved:fetch"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # ------------------------------------------------------------------- lua
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
    "go": (
        code_go,
        [
            Scenario(
                "simple",
                "s1.go",
                "package main\n"
                'import "fmt"\n'
                "func helper() int { return 1 }\n"
                "func main() { helper(); fmt.Println(1) }\n",
                funcs={"helper", "main"},
                edges=[
                    ("imports", "s1.go", "fmt"),
                    ("calls", "main", "helper"),
                ],
            ),
            Scenario(
                "nested",
                "s2.go",
                "package shapes\n"
                "type Render interface { Draw() }\n"
                "type Shape struct{ X int }\n"
                "func (s Shape) Draw() {}\n"
                "func (s *Shape) Area() float64 { return 0 }\n",
                funcs={"Draw", "Area"},
                classes={"Render", "Shape"},
                edges=[],
            ),
            Scenario(
                "realworld",
                "s3.go",
                "package svc\n"
                'import (\n  "errors"\n  "time"\n)\n'
                "// func decoy() {} — commented out\n"
                "type Service struct{ id int }\n"
                "func validate() error { return errors.New(`func fake_fn() {}`) }\n"
                "func (s *Service) Run(t time.Time) {\n"
                "  validate()\n"
                "}\n",
                funcs={"validate", "Run"},
                classes={"Service"},
                edges=[
                    ("imports", "s3.go", "errors"),
                    ("calls", "Run", "validate"),
                ],
                has_decoys=True,
            ),
        ],
    ),
    # -------------------------------------------------------------------- ts
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


# ---------------------------------------------------------------------------
# Config-format corpora (yaml / json / toml) — exact-label ground truth.
# These extractors claim config KEYS and manifest DEPENDENCIES, so the metric
# is exact set equality of emitted labels (recall AND precision in one check).
# Designed scope (pinned, not a gap): arbitrary non-manifest .json files yield
# no key nodes by design — only known manifests (package.json, .mcp.json,
# tsconfig.json) are mined, to keep the graph lean (P3).
# ---------------------------------------------------------------------------

# dependency = the manifest node itself; doc:external = the dep-target stubs
# (promoted ends of `imports` edges); tool = scripts; contract = tsconfig
# paths. Exact-set equality over these kinds pins recall AND precision.
_CONFIG_KINDS = {"doc:frontmatter_key", "dependency", "tool", "doc:external", "contract"}

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


def _config_labels(result) -> set[str]:
    return {n.label for n in result.nodes if n.kind in _CONFIG_KINDS and n.label}


_CONFIG_CASES = [(fmt, sc) for fmt, (_, scenarios) in CONFIG_CORPUS.items() for sc in scenarios]
_CONFIG_IDS = [f"{fmt}-{sc.name}" for fmt, sc in _CONFIG_CASES]


@pytest.mark.parametrize("fmt,sc", _CONFIG_CASES, ids=_CONFIG_IDS)
def test_config_label_recall_and_precision(fmt, sc):
    """Config formats: emitted key/dependency labels must EXACTLY equal the
    ground truth — full recall (nothing missed) AND full precision (nothing
    phantom) in one assertion."""
    mod = CONFIG_CORPUS[fmt][0]
    result = mod.extract(sc.file, sc.src)
    got = _config_labels(result)
    missing = sc.funcs - got
    phantom = got - sc.funcs
    assert not missing, f"{fmt}/{sc.name}: missing labels {missing}"
    assert not phantom, f"{fmt}/{sc.name}: phantom labels {phantom}"


@pytest.mark.parametrize("fmt", list(CONFIG_CORPUS), ids=list(CONFIG_CORPUS))
def test_config_speed_and_memory(fmt):
    mod, scenarios = CONFIG_CORPUS[fmt]
    times: list[float] = []
    peaks: list[int] = []
    for sc in scenarios:
        for _ in range(5):
            tracemalloc.start()
            t0 = time.perf_counter()
            mod.extract(sc.file, sc.src)
            times.append((time.perf_counter() - t0) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
    assert statistics.median(times) <= 25
    assert max(peaks) <= 6 * 1024 * 1024


def _run_case(mod, sc: Scenario):
    return mod.extract(sc.file, sc.src)


def _symbol_metrics(result, sc: Scenario) -> tuple[float, float, set[str]]:
    extracted = _extracted_names(result, _FUNC_KINDS) | _extracted_names(result, _CLASS_KINDS)
    expected = sc.funcs | sc.classes
    found = {e for e in expected if e in extracted}
    recall = len(found) / len(expected) if expected else 1.0
    phantoms = {
        n
        for n in extracted
        if n not in expected
        # constructors legitimately share the class name (java/c#)
        and n not in sc.classes
    }
    precision = (len(extracted) - len(phantoms)) / len(extracted) if extracted else 1.0
    return recall, precision, phantoms


def _edge_recall(result, sc: Scenario) -> float:
    if not sc.edges:
        return 1.0
    hits = 0
    for etype, src_frag, tgt_frag in sc.edges:
        if any(
            e.edge_type == etype and src_frag in e.source_uid and tgt_frag in e.target_uid
            for e in result.edges
        ):
            hits += 1
    return hits / len(sc.edges)


def compute_stats() -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for lang, (mod, scenarios) in CORPUS.items():
        recalls: list[float] = []
        precisions: list[float] = []
        edge_recalls: list[float] = []
        times_ms: list[float] = []
        peaks: list[int] = []
        for sc in scenarios:
            result = _run_case(mod, sc)
            r, p, _ = _symbol_metrics(result, sc)
            recalls.append(r)
            precisions.append(p)
            edge_recalls.append(_edge_recall(result, sc))
            for _ in range(5):
                tracemalloc.start()
                t0 = time.perf_counter()
                _run_case(mod, sc)
                times_ms.append((time.perf_counter() - t0) * 1000)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peaks.append(peak)
        stats[lang] = {
            "symbol_recall": min(recalls),
            "precision": min(precisions),
            "edge_recall": min(edge_recalls),
            "median_ms": statistics.median(times_ms),
            "peak_kb": max(peaks) / 1024,
        }
    for fmt, (mod, scenarios) in CONFIG_CORPUS.items():
        recalls = []
        precisions = []
        times_ms = []
        peaks = []
        for sc in scenarios:
            result = mod.extract(sc.file, sc.src)
            got = _config_labels(result)
            recalls.append(len(got & sc.funcs) / len(sc.funcs) if sc.funcs else 1.0)
            precisions.append(len(got & sc.funcs) / len(got) if got else 1.0)
            for _ in range(5):
                tracemalloc.start()
                t0 = time.perf_counter()
                mod.extract(sc.file, sc.src)
                times_ms.append((time.perf_counter() - t0) * 1000)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peaks.append(peak)
        stats[fmt] = {
            "symbol_recall": min(recalls),
            "precision": min(precisions),
            "edge_recall": 1.0,  # n/a for config formats (no call/inherit edges)
            "median_ms": statistics.median(times_ms),
            "peak_kb": max(peaks) / 1024,
        }
    return stats


# ---------------------------------------------------------------------------
# Threshold gates — these are the score, asserted
# ---------------------------------------------------------------------------

_ALL_CASES = [(lang, sc) for lang, (_, scenarios) in CORPUS.items() for sc in scenarios]
_IDS = [f"{lang}-{sc.name}" for lang, sc in _ALL_CASES]


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_symbol_recall_and_precision(lang, sc):
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    recall, precision, phantoms = _symbol_metrics(result, sc)
    assert recall >= 0.9, f"{lang}/{sc.name}: symbol recall {recall:.2f} < 0.9"
    assert precision >= 0.95, f"{lang}/{sc.name}: precision {precision:.2f} (phantoms={phantoms})"


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_no_decoy_leakage(lang, sc):
    """Code inside comments / string literals must never become a symbol."""
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    extracted = _extracted_names(result, _FUNC_KINDS | _CLASS_KINDS)
    leaked = extracted & _DECOY_NAMES
    assert not leaked, f"{lang}/{sc.name}: decoys extracted from comments/strings: {leaked}"


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_edge_recall(lang, sc):
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    er = _edge_recall(result, sc)
    assert er >= 0.8, f"{lang}/{sc.name}: edge recall {er:.2f} < 0.8"


@pytest.mark.parametrize("lang", list(CORPUS), ids=list(CORPUS))
def test_call_confidence_calibration(lang):
    """Trust: every calls edge at conf ≥ 0.9 must resolve to a real same-file
    uid — a high-confidence edge pointing at an external guess is calibration
    inflation (graph-os-authoring §3)."""
    mod, scenarios = CORPUS[lang]
    for sc in scenarios:
        result = _run_case(mod, sc)
        node_uids = {n.uid for n in result.nodes}
        for e in result.edges:
            if e.edge_type == "calls" and e.confidence >= 0.9:
                assert not e.target_uid.startswith("code:external"), (
                    f"{lang}/{sc.name}: conf {e.confidence} call -> {e.target_uid}"
                )
                assert e.target_uid in node_uids


@pytest.mark.parametrize("lang", list(CORPUS), ids=list(CORPUS))
def test_speed_and_memory(lang):
    mod, scenarios = CORPUS[lang]
    times: list[float] = []
    peaks: list[int] = []
    for sc in scenarios:
        for _ in range(5):
            tracemalloc.start()
            t0 = time.perf_counter()
            _run_case(mod, sc)
            times.append((time.perf_counter() - t0) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
    median_ms = statistics.median(times)
    peak_mb = max(peaks) / (1024 * 1024)
    assert median_ms <= 25, f"{lang}: median {median_ms:.1f} ms > 25 ms"
    assert peak_mb <= 6, f"{lang}: peak {peak_mb:.1f} MB > 6 MB"


def test_kotlin_grammar_quirk_is_surfaced():
    """Known upstream limitation, pinned (minimal repro): tree-sitter-kotlin
    1.1.0 mis-parses a SINGLE-LINE class body with members when it follows any
    other declaration — `class A { fun x() {} }` + `class B { fun y() {} }`
    on consecutive lines collapses into an ERROR node (multiline bodies are
    fine). The extractor must fail OPEN: file node + a surfaced parse error
    (TASK-293 machinery), never a raise, and salvaged symbols still emitted."""
    pytest.importorskip("tree_sitter_kotlin")
    src = "class A { fun x() {} }\nclass B { fun y() {} }\n"
    result = code_generic.extract("quirk.kt", src)
    assert any(p.kind == "tree_sitter_error" for p in result.parse_errors), (
        "expected the single-line-class-body quirk to surface as a parse "
        "error; if this fails the upstream grammar got fixed — delete this "
        "pin and tighten the kotlin corpus"
    )
    # fail-open: file node still present, salvaged symbols still extracted
    assert any(n.kind == "code:file" for n in result.nodes)
    assert "x" in _extracted_names(result, _FUNC_KINDS)


if __name__ == "__main__":
    table = compute_stats()
    print(
        f"{'lang':10} {'sym_recall':>10} {'precision':>10} {'edge_recall':>11} "
        f"{'median_ms':>10} {'peak_kb':>8}"
    )
    for lang, row in table.items():
        print(
            f"{lang:10} {row['symbol_recall']:>10.2f} {row['precision']:>10.2f} "
            f"{row['edge_recall']:>11.2f} {row['median_ms']:>10.2f} {row['peak_kb']:>8.0f}"
        )
