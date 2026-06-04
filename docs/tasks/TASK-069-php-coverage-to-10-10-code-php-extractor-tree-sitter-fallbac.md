---
id: TASK-069
title: "PHP coverage to 10/10: code_php extractor (tree-sitter+fallback) + Laravel/WordPress/WHMCS contracts"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, extractors, php, laravel, wordpress, whmcs, polyglot]
status: in_progress
priority: P2
appetite: "3d"
created: 2026-06-04
started: 2026-06-03
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-069: PHP coverage to 10/10: code_php extractor (tree-sitter+fallback) + Laravel/WordPress/WHMCS contracts

**Outcome (one sentence):** PHP reaches Python-gold parity in the graph: new code_php extractor (tree-sitter-php primary + regex fallback) emitting namespace/class/interface/trait/method/function/property/const nodes + use-imports + extends/implements/use-trait + typed param/return/property edges + PHP-8 attributes + same-file resolved calls/constructs. Plus contracts scanners for Laravel (Route facade incl resource/groups/middleware + controller handler edges + models/commands), WordPress (add_action/add_filter/do_action/apply_filters + shortcode + register_post_type + register_rest_route + wp_ajax), and WHMCS (add_hook + module-function convention + module-type classification). Each group adversarial-tested + graph_os matrix verified + force-reindex smoke errors=0.

## Read First
- docs/playbooks/polyglot-extractor-roadmap.md
- src/core/graph_os/extractors/code_go.py
- src/core/graph_os/extractors/contracts.py
- src/core/graph_os/tree_sitter_overlay.py
- src/core/graph_os/tools/reindex_dispatch.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a `.php` file with namespace/class/interface/trait/method/function/typed-property, **When** `code_php` extracts it, **Then** it emits the matching nodes + `imports`(use)/`inherits_from`(extends)/`implements`/`uses_trait`/`has_param_type`/`returns_type`/`field_of_type`/`is_decorated_by`(#[Attr]) edges, and same-file `B()`/`$this->m()`/`self::m()`/`new X()` resolve to real uids (Python `same_scope` parity).
- **Given** the tree-sitter-php grammar is absent, **When** `code_php` runs, **Then** the regex fallback still emits file/namespace/class/function nodes (no crash).
- **Given** a Laravel file, **When** contracts extracts it, **Then** `Route::get/post/...`, `resource`/`apiResource`, and `prefix/group/middleware` produce http routes with controller→handler edges.
- **Given** a WordPress file, **When** contracts extracts it, **Then** `add_action`/`add_filter` → events, `add_shortcode`/`register_post_type`/`register_rest_route`/`wp_ajax_*` produce the matching nodes.
- **Given** a WHMCS file, **When** contracts extracts it, **Then** `add_hook(...)` → events and `{module}_{Action}` functions are tagged module functions with module-type classification.
- **Given** all the above, **When** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` runs and `cos graph-reindex --force` runs, **Then** tests are green (new adversarial suites incl) and reindex reports `errors=0`.

## Work Log
