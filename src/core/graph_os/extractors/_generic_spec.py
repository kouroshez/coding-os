"""code_generic — the curated language tables the polyglot extractor is built on.

Extension routing plus the per-language tree-sitter node types that denote a
function-like or class-like definition. Data only, imports nothing local: the
node walk, the edge hooks, and the facade all read from here, so adding a
language stays a one-row change in one file.
"""

from __future__ import annotations

EXTRACTOR_ID = "code_generic@v1"

# Extension → overlay language id. Several extensions map to one grammar
# (.cc/.cpp/.hpp → cpp). The grammar must be registered in
# tree_sitter_overlay._LOADERS for the language to actually parse.
EXT_TO_LANG: dict[str, str] = {
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "c_sharp",
    ".scala": "scala",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
}

# Per-language tree-sitter node types that denote a function-like or
# class-like definition. Curated (not heuristic) so coverage is honest and
# reliable — ruby names methods `method`, rust uses `function_item`, etc.
_LANG_SPEC: dict[str, dict[str, frozenset[str]]] = {
    "rust": {
        # impl_item is intentionally excluded — it duplicates the struct/enum
        # name as a phantom class. Methods inside an impl are still captured
        # (they attach to the file); linking impl→type is per-language work.
        "func": frozenset({"function_item", "function_signature_item"}),
        "class": frozenset({"struct_item", "enum_item", "trait_item", "mod_item"}),
    },
    "ruby": {
        "func": frozenset({"method", "singleton_method"}),
        "class": frozenset({"class", "module"}),
    },
    "java": {
        "func": frozenset({"method_declaration", "constructor_declaration"}),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration",
            }
        ),
    },
    "c": {
        "func": frozenset({"function_definition"}),
        "class": frozenset({"struct_specifier", "union_specifier", "enum_specifier"}),
    },
    "cpp": {
        "func": frozenset({"function_definition"}),
        "class": frozenset(
            {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier"}
        ),
    },
    "c_sharp": {
        "func": frozenset(
            {"method_declaration", "constructor_declaration", "local_function_statement"}
        ),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "struct_declaration",
                "enum_declaration",
                "record_declaration",
            }
        ),
    },
    "scala": {
        "func": frozenset({"function_definition"}),
        "class": frozenset({"class_definition", "object_definition", "trait_definition"}),
    },
    "kotlin": {
        "func": frozenset({"function_declaration"}),
        "class": frozenset({"class_declaration", "object_declaration"}),
    },
    "lua": {
        # Lua has no classes — functions only (tables are runtime constructs).
        "func": frozenset({"function_declaration"}),
        "class": frozenset(),
    },
}

_NAME_NODE_TYPES = ("identifier", "type_identifier", "constant", "name", "field_identifier")

_DECLARATOR_NAME_TYPES = (
    "identifier",
    "field_identifier",
    "type_identifier",
    "qualified_identifier",
    "destructor_name",
    "operator_name",
)
