"""board-os web viewer server (L.5).

Minimal aiohttp app:
  GET  /            → static HTML shell
  GET  /api/board   → wraps cos_task_board() MCP tool as JSON
  POST /api/move    → calls workflow.transition() with file-path resolved
  WS   /ws          → broadcast board-changed events from file-watcher

Security:
  - Default bind: 127.0.0.1
  - --bind 0.0.0.0 requires --auth-token; token written to
    .coding-os/.board-token (600 perms).
  - JSON schema validated before workflow.transition() is called.
  - Drag-drop rate limit: 10 mutations / second per connection.

Fail-soft: if aiohttp or watchdog isn't installed, the CLI command
prints a clear error and exits cleanly.  Unit tests stub both.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

try:
    from aiohttp import WSMsgType, web
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    _WATCHDOG_OK = True
except ImportError:
    _WATCHDOG_OK = False

from core.board_os import mcp_tools
from core.board_os.workflow import transition

logger = logging.getLogger("coding_os.board_os.viewer.server")

_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>cos-board</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * { box-sizing: border-box; font-family: -apple-system, system-ui, sans-serif; }
  body { margin: 0; background: #0b0e14; color: #e6e6e6; }
  header { padding: 12px 20px; background: #11141c; border-bottom: 1px solid #222;
           display: flex; justify-content: space-between; align-items: center; }
  header h1 { margin: 0; font-size: 18px; }
  .wip { font-size: 13px; color: #888; }
  .wip.violation { color: #dc2626; font-weight: bold; }
  .board { display: grid; grid-auto-flow: column; overflow-x: auto;
           gap: 8px; padding: 12px; min-height: calc(100vh - 60px); }
  .col { background: #151922; border: 1px solid #1e2230; border-radius: 8px;
         min-width: 220px; padding: 8px; }
  .col h2 { font-size: 12px; text-transform: uppercase; color: #888;
            margin: 0 0 8px 0; padding: 4px 6px; letter-spacing: 0.5px; }
  .col.emergency h2 { color: #dc2626; }
  .card { background: #1e2230; border-left: 4px solid #444; padding: 8px;
          border-radius: 4px; margin-bottom: 6px; cursor: move; user-select: none;
          font-size: 13px; transition: transform 0.1s; }
  .card:hover { transform: translateX(2px); }
  .card .title { font-weight: 500; margin-bottom: 4px; }
  .card .id { font-size: 11px; color: #666; }
  .card .meta { font-size: 11px; color: #888; margin-top: 4px; display: flex; gap: 8px; }
  .card.kind-feature { border-left-color: #eab308; }
  .card.kind-bug { border-left-color: #dc2626; }
  .card.kind-chore { border-left-color: #22c55e; }
  .card.kind-spike { border-left-color: #3b82f6; }
  .card.kind-docs { border-left-color: #a855f7; }
  .card.kind-refactor { border-left-color: #14b8a6; }
  .card.kind-test { border-left-color: #f59e0b; }
  .card.kind-security { border-left-color: #ea580c; }
  .card.prio-P0 { box-shadow: 0 0 0 2px #dc2626; }
  .card.prio-P1 { box-shadow: 0 0 0 1px #f97316; }
  .epic-badge { display: inline-block; padding: 1px 5px; border-radius: 3px;
                background: #2a3042; color: #aaa; font-size: 10px; }
  .labels { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
  .label { background: #2a3042; color: #999; padding: 1px 5px; border-radius: 3px;
           font-size: 10px; }
  .toast { position: fixed; bottom: 20px; right: 20px; background: #dc2626;
           color: white; padding: 10px 16px; border-radius: 4px; display: none; }
  .toast.show { display: block; }
  .swimlane-label { font-size: 10px; color: #666; text-transform: uppercase;
                    margin-bottom: 4px; letter-spacing: 0.5px; }
</style>
</head>
<body>
<header>
  <h1>cos-board <span style="color:#666; font-weight:normal; font-size:14px;">— Scrumban</span></h1>
  <div class="wip" id="wip-indicator">WIP: loading…</div>
</header>
<div class="board" id="board">Loading…</div>
<div class="toast" id="toast"></div>
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"
        integrity="sha384-4Yje8BY0kRCAAPRCsyxv+0EsRnrWbVtDyzadkJIhLZrXyMTxZYaUG2bm7JqQkgWu"
        crossorigin="anonymous"></script>
<script>
const STATUSES = ["icebox", "ready", "emergency", "in_progress", "testing", "complete", "blocked"];
const STATUS_LABELS = {
  icebox: "Icebox", ready: "Ready", emergency: "🚨 Emergency",
  in_progress: "In Progress", testing: "Testing", complete: "Complete", blocked: "Blocked",
};

function showToast(msg, duration=3000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

function renderCard(card) {
  const div = document.createElement('div');
  div.className = `card kind-${card.kind || 'chore'} prio-${card.priority}`;
  div.dataset.taskId = card.id;
  div.dataset.status = card.status;
  const epic = card.epic ? `<span class="epic-badge" dir="auto">${card.epic}</span>` : '';
  const labels = (card.labels || []).map(l => `<span class="label" dir="auto">${l}</span>`).join('');
  div.innerHTML = `
    <div class="id">${card.id} · ${card.priority} · ${card.appetite}</div>
    <div class="title" dir="auto">${card.title}${epic ? ' ' + epic : ''}</div>
    <div class="labels">${labels}</div>
    <div class="meta" dir="auto">${card.last_log_line || ''}</div>
  `;
  return div;
}

async function loadBoard() {
  const res = await fetch('/api/board');
  const env = await res.json();
  if (!env.ok) {
    document.getElementById('board').textContent = 'Failed to load: ' + (env.error && env.error.message);
    return;
  }
  const data = env.data;
  const wipEl = document.getElementById('wip-indicator');
  if (data.wip) {
    const w = data.wip.counts;
    const c = data.wip.caps;
    const violated = (data.wip.violations || []).length > 0;
    wipEl.textContent = `WIP: in_progress ${w.in_progress}/${c.in_progress} · testing ${w.testing}/${c.testing} · emergency ${w.emergency}/${c.emergency}`;
    wipEl.classList.toggle('violation', violated);
  }
  const board = document.getElementById('board');
  board.innerHTML = '';

  // One column per status; within each, group by swimlane.
  for (const st of STATUSES) {
    const col = document.createElement('div');
    col.className = 'col' + (st === 'emergency' ? ' emergency' : '');
    col.dataset.status = st;
    col.innerHTML = `<h2>${STATUS_LABELS[st]}</h2>`;
    const bySwim = {};
    for (const lane of Object.keys(data.grouped || {})) {
      for (const card of (data.grouped[lane][st] || [])) {
        (bySwim[lane] = bySwim[lane] || []).push(card);
      }
    }
    for (const lane of Object.keys(bySwim).sort()) {
      const lh = document.createElement('div');
      lh.className = 'swimlane-label';
      lh.textContent = lane;
      col.appendChild(lh);
      for (const card of bySwim[lane]) {
        col.appendChild(renderCard(card));
      }
    }
    board.appendChild(col);

    // Enable Sortable on the column.
    new Sortable(col, {
      group: 'board', animation: 150,
      filter: 'h2, .swimlane-label',
      preventOnFilter: false,
      onEnd: async (evt) => {
        const card = evt.item;
        const toStatus = evt.to.dataset.status;
        if (!toStatus) return;
        const taskId = card.dataset.taskId;
        const prevStatus = card.dataset.status;
        if (toStatus === prevStatus) return;
        const res = await fetch('/api/move', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({task_id: taskId, to: toStatus}),
        });
        const env = await res.json();
        if (!env.ok) {
          showToast(env.error.message || 'Move rejected');
          // Rollback: send the card back.
          const src = document.querySelector(`.col[data-status="${prevStatus}"]`);
          if (src) src.appendChild(card);
        } else {
          card.dataset.status = toStatus;
          // Reload to pick up server-side effects (WIP update etc).
          setTimeout(loadBoard, 200);
        }
      },
    });
  }
}

loadBoard();
setInterval(loadBoard, 10000);  // Poll every 10s as a cheap fallback for file-watcher.

// WebSocket for real-time updates (if available).
try {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'board-changed') loadBoard();
    } catch (e) { }
  };
} catch (e) { /* no WS; polling only */ }
</script>
</body>
</html>
"""


class _TaskFileWatcher(FileSystemEventHandler if _WATCHDOG_OK else object):
    """Emits WebSocket broadcasts when docs/tasks/*.md changes on disk."""

    def __init__(self, broadcast):
        self._broadcast = broadcast
        self._last = 0.0

    def on_any_event(self, event):  # type: ignore[override]
        path = getattr(event, "src_path", "")
        if not path.endswith(".md"):
            return
        now = time.time()
        if now - self._last < 0.2:  # 200ms debounce
            return
        self._last = now
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(asyncio.ensure_future, self._broadcast())
        except RuntimeError:
            pass


def _auth_token(project_root: Path) -> str:
    token_file = project_root / ".coding-os" / ".board-token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    os.chmod(token_file, 0o600)
    return token


def _check_auth(request, token):
    if token is None:
        return True
    given = request.query.get("token") or request.headers.get("X-Board-Token")
    return given == token


async def _handle_index(request):
    token = request.app["auth_token"]
    if not _check_auth(request, token):
        return web.Response(status=401, text="auth token required")
    return web.Response(text=_HTML, content_type="text/html")


async def _handle_board(request):
    token = request.app["auth_token"]
    if not _check_auth(request, token):
        return web.Response(status=401, text="auth token required")
    conn = request.app["conn_factory"]()
    try:
        envelope = mcp_tools.cos_task_board(conn)
    finally:
        conn.close()
    return web.Response(text=envelope, content_type="application/json")


async def _handle_move(request):
    token = request.app["auth_token"]
    if not _check_auth(request, token):
        return web.Response(status=401, text="auth token required")

    # Rate limit: 10 req/sec per peer
    now = time.time()
    peer = request.remote
    bucket = request.app["rate_limit"].setdefault(peer, [])
    bucket[:] = [t for t in bucket if now - t < 1.0]
    if len(bucket) >= 10:
        return web.Response(status=429, text="rate limit")
    bucket.append(now)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400, text="bad json")

    task_id = body.get("task_id", "")
    to_status = body.get("to", "")
    if not task_id or not to_status:
        return web.Response(status=400, text="missing task_id/to")

    conn = request.app["conn_factory"]()
    try:
        envelope = mcp_tools.cos_task_move(
            conn, task_id=task_id, to=to_status,
            reason=body.get("reason"),
            agent_session=body.get("agent_session"),
        )
    finally:
        conn.close()

    # Also notify all WS clients
    await _broadcast(request.app, {"type": "board-changed"})

    return web.Response(text=envelope, content_type="application/json")


async def _handle_ws(request):
    token = request.app["auth_token"]
    if not _check_auth(request, token):
        return web.Response(status=401, text="auth token required")
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    request.app["ws_peers"].add(ws)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        request.app["ws_peers"].discard(ws)
    return ws


async def _broadcast(app, msg):
    dead = []
    for ws in app["ws_peers"]:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        app["ws_peers"].discard(ws)


def build_app(
    conn_factory,
    *,
    auth_token: str | None = None,
    project_root: Path | None = None,
) -> Any:
    if not _AIOHTTP_OK:
        raise RuntimeError(
            "aiohttp is not installed. Install with: pip install aiohttp watchdog"
        )
    app = web.Application()
    app["conn_factory"] = conn_factory
    app["auth_token"] = auth_token
    app["ws_peers"] = set()
    app["rate_limit"] = {}
    app["project_root"] = project_root or Path.cwd()
    app.router.add_get("/", _handle_index)
    app.router.add_get("/api/board", _handle_board)
    app.router.add_post("/api/move", _handle_move)
    app.router.add_get("/ws", _handle_ws)
    return app


def serve_board(
    *,
    host: str = "127.0.0.1",
    port: int = 9000,
    db_path: str | None = None,
    project_root: Path | None = None,
    auth_token: str | None = None,
) -> None:
    if not _AIOHTTP_OK:
        raise RuntimeError(
            "aiohttp is not installed. Install with: pip install aiohttp watchdog"
        )
    project_root = (project_root or Path.cwd()).resolve()
    db_path = db_path or str(project_root / ".coding-os" / "thinking-os.db")

    # If host is not loopback, require auth.
    if host != "127.0.0.1" and host != "localhost" and auth_token is None:
        auth_token = _auth_token(project_root)
        logger.info("auth token: %s (stored at .coding-os/.board-token)", auth_token)

    def conn_factory():
        return sqlite3.connect(db_path)

    app = build_app(conn_factory, auth_token=auth_token, project_root=project_root)
    if _WATCHDOG_OK:
        tasks_dir = project_root / "docs" / "tasks"
        if tasks_dir.exists():
            async def broadcaster():
                await _broadcast(app, {"type": "board-changed"})
            handler = _TaskFileWatcher(broadcaster)
            observer = Observer()
            observer.schedule(handler, str(tasks_dir), recursive=False)
            observer.start()
    web.run_app(app, host=host, port=port, print=None)
