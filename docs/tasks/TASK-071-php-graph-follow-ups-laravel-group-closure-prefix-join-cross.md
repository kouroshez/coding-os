---
id: TASK-071
title: "PHP graph follow-ups: Laravel group-closure prefix join + cross-file controller handler resolution + real-world WordPress validation"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, php, laravel, wordpress, contracts]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-03
completed: 2026-06-03
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-071: PHP graph follow-ups: Laravel group-closure prefix join + cross-file controller handler resolution + real-world WordPress validation

**Outcome (one sentence):** Close the two documented PHP limitations from TASK-069: (1) Laravel routes inside Route::prefix()->group() / Route::group(['prefix'=>..]) closures get their group prefix joined (brace-matched scoping, nesting-aware); (2) cross-file controller handlers ([Ctrl::class,'m'] / 'Ctrl@m') resolve to the real code:method node via a new backend link_php_handlers post-pass. Validate end-to-end on real WordPress code downloaded into a cos-init project in /tmp (hooks/shortcodes/REST routes extracted correctly). Align docs.

## Read First
- src/core/graph_os/extractors/contracts.py
- src/core/graph_os/backends/sqlite_backend.py
- src/core/graph_os/tools/reindex_dispatch.py
- docs/playbooks/polyglot-extractor-roadmap.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `Route::prefix('api')->group(function(){ Route::get('/users', ...); })` (and the `Route::group(['prefix'=>'api'], ...)` form, and nested groups), **When** contracts extracts it, **Then** the inner route URL is `/api/users` (group prefix joined, nesting-aware), with no false prefixes on routes outside the closure.
- **Given** `Route::get('/u', [UserController::class,'index'])` in routes/web.php and `class UserController { function index(){} }` in another file, **When** the graph is reindexed, **Then** the route→handler edge resolves to the real `code:method:…::UserController.index` node (via a new `link_php_handlers` post-pass), not an unresolved stub.
- **Given** real WordPress code downloaded into a `cos init` project in /tmp, **When** `cos graph-reindex` runs, **Then** WP hooks/shortcodes/REST routes are extracted (errors=0) and queryable.
- **Given** the changes, **When** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` runs, **Then** green with new regression tests; docs §4.9 updated to drop the two limitations.

## Work Log
- 2026-06-04 [claude]: Closed both PHP limits: Fix1 Laravel group-closure prefix join (brace-matched, nesting-aware, fluent+array forms); Fix2 
