"""Shared router, project-root resolution and `cos` subprocess plumbing.

Leaf of the config route package: the two endpoint modules import this and
never each other, so importing either one registers its routes on the single
APIRouter defined here.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])


def _project_root() -> Path:
    from web._project_context import current_project_root

    return current_project_root()


def _project_config_skill_list(key: str) -> list[str]:
    try:
        import yaml

        config_path = _project_root() / ".coding-os.yaml"
        if not config_path.is_file():
            return []
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return list(config.get(key) or [])
    except Exception as exc:
        logger.debug("%s read failed: %s", key, exc)
        return []


# Ids reach a subprocess argv or a file path, so restrict them to a slug — a
# leading dash can't then be parsed as a CLI option, nor a slash escape a path.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_id(value: str) -> bool:
    return bool(_SLUG_RE.match(value or ""))


# Curated first-party stdio MCP servers (no secret / extra config needed). The
# pre-Extension-Manager allow-list; the EM registry supersedes it with the
# trust / SSRF / upload machinery for custom + remote servers.
_MCP_ALLOWLIST: list[dict] = [
    {
        "id": "fetch",
        "name": "Fetch",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "description": "Fetch a URL and return its content as markdown.",
    },
    {
        "id": "git",
        "name": "Git",
        "command": "uvx",
        "args": ["mcp-server-git"],
        "description": "Read, search, and inspect a local git repository.",
    },
    {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "description": "A structured step-by-step reasoning scratchpad.",
    },
    {
        "id": "playwright",
        "name": "Playwright",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "description": "Drive a real browser for end-to-end testing and scraping.",
    },
    {
        "id": "context7",
        "name": "Context7",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "description": "Up-to-date, version-specific library docs and code examples.",
    },
]


def _cos_bin() -> list[str]:
    found = shutil.which("cos")
    return [found] if found else [sys.executable, "-m", "cli.main"]


def _cos_root() -> Path | None:
    """coding-os package root — the safe cwd for the `python -m cli.main` fallback,
    so a target project's own top-level cli/ can never shadow the real cos."""
    try:
        from cli.list_stacks import TEMPLATES_DIR

        return TEMPLATES_DIR.parent.parent
    except Exception as exc:
        logger.debug("cos root resolution failed: %s", exc)
        return None


def _parse_cos_json(stdout: str) -> dict:
    """Parse a `cos --format json` payload: whole stdout first (indent=2 is
    multi-line), then the last `{`-prefixed line for single-line emitters."""
    text = stdout.strip()
    if not text:
        return {}
    try:
        whole = json.loads(text)
        if isinstance(whole, dict):
            return whole
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        cand = line.strip()
        if cand.startswith("{"):
            try:
                parsed = json.loads(cand)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return {}


def _run_cos(args: list[str], timeout: int = 300) -> tuple[bool, dict, str]:
    """Run `cos <args>` from the coding-os root; return (ok, json-payload, error).

    The project is addressed via an explicit `-d <path>` arg, not cwd, so the
    subprocess cwd stays on the coding-os tree (see _cos_root)."""
    root = _cos_root()
    try:
        proc = subprocess.run(
            [*_cos_bin(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root) if root else None,
        )
    except subprocess.TimeoutExpired:
        return False, {}, f"'{' '.join(args)}' timed out after {timeout}s"
    except OSError as exc:
        return False, {}, f"could not launch cos: {exc}"
    if proc.returncode != 0:
        return False, {}, (proc.stderr or proc.stdout or "command failed").strip()[-400:]
    return True, _parse_cos_json(proc.stdout or ""), ""


def _fail(status: int, category: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": {"category": category, "message": message}},
    )


def _ok(data: dict) -> JSONResponse:
    return JSONResponse(content={"ok": True, "data": data})


def _audit(root: Path, action: str, unit: str, detail: str = "") -> None:
    """Append a what·which·when row per mutation (extension-manager.md § Hub auth)."""
    try:
        from datetime import datetime, timezone

        log = root / ".coding-os" / "extensions-audit.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "unit": unit,
            "detail": detail,
        }
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        logger.debug("audit append failed: %s", exc)
