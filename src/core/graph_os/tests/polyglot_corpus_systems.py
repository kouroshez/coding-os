"""Polyglot extractor corpus — compiled and JVM languages.

Per-language source snippets the extractor quality tests measure recall
and precision against. Data, not logic: each language entry changes alone.
"""

from __future__ import annotations

from graph_os.tests.polyglot_scenario import Scenario

from graph_os.extractors import (
    code_generic,
    code_go,
)

CORPUS: dict[str, tuple[object, list[Scenario]]] = {
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
}
