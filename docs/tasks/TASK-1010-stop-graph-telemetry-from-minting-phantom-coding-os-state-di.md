---
id: TASK-1010
title: "Stop graph telemetry from minting phantom .coding-os state dirs at cwd"
swimlane: "graph_os"
kind: bug
epic: null
labels: [incident, disk, state-files, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1010: Stop graph telemetry from minting phantom .coding-os state dirs at cwd

**Outcome (one sentence):** A `cos_graph_*` call from a subdirectory writes telemetry into the real project state dir instead of creating a phantom one that permanently hijacks state resolution for that subtree.

## Read First
- src/core/graph_os/tools/_graph_envelope.py
- src/core/thinking_os/_db_paths.py

## Repro Steps
Two stray state trees existed in the repo: `src/core/web/ui/.coding-os` (with its own `coding-os.db`, `-wal`, `-shm`, `.cos.log`) and `src/core/thinking_os/.coding-os`. Source: `_graph_envelope._telemetry_path()` falls back to `_Path.cwd() / ".coding-os"` when `COS_STATE_DIR` is unset, then calls `path.mkdir(parents=True, exist_ok=True)` — minting a state dir wherever the process happens to be. The comment claims "repo-rooted" but cwd is not the repo root.

Once minted the dir poisons resolution permanently: `source cos-env.sh` from `src/core/web/ui` resolved `COS_STATE_DIR` to the phantom path. After deleting it the same command correctly resolved to the repo root and did **not** recreate it — proving the shell marker-walk is right and the Python fallback is the sole creator.

`thinking_os._db_paths._find_project_root_from_cwd` already implements the correct walk and its docstring names this exact failure (TASK-117); `resolve_db_path`'s docstring says "Do NOT weaken this to a cwd fallback".

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** `COS_STATE_DIR` is unset and cwd is a subdirectory of a coding-os project, **When** `_telemetry_path` resolves, **Then** it returns the repo-root `.coding-os` path and creates no directory at cwd.
- **Given** cwd is not inside any coding-os project, **When** `_telemetry_path` resolves, **Then** it returns `None` and writes nothing rather than minting a state dir.
- **Given** `COS_STATE_DIR` is set, **When** `_telemetry_path` resolves, **Then** it still honours the env var unchanged.

## Work Log
- 2026-08-17 [claude]: Edit state-files.md
- 2026-08-17 [claude]: Edit _graph_envelope.py
- 2026-08-17 [claude]: Edit test_telemetry_path_resolution.py
- 2026-08-17 [claude]: Edit test_telemetry_path_resolution.py
- 2026-08-17 [claude]: Edit test_telemetry_path_resolution.py
- 2026-08-17 [claude]: Edit test_telemetry_path_resolution.py
- 2026-08-17 [claude]: commit 1bc01fcb96 — fix(hub): stop hub.log growing without bound
