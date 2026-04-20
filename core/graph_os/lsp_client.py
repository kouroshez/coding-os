"""Minimal LSP 3.17 stdio client (Phase I.14).

PURPOSE:  Talk to a local language server (pyright, tsserver, gopls)
          over the wire protocol defined in
          https://microsoft.github.io/language-server-protocol/specifications/specification-3-17/.
INPUT:    subprocess command + project root.
OUTPUT:   A small client that supports `initialize`, `textDocument/
          didOpen`, `textDocument/definition`, and `shutdown/exit`.
DEPENDS:  stdlib only.
NOTES:    The goal is not to be a fully-general LSP client — it's to
          honour the overlay contract from plan §7.4 and raise
          precision on symbol resolution from ≥85% to ≥95%. We only
          implement what `LspDriver.resolve()` needs.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("graph_os.lsp_client")


class LspClientError(RuntimeError):
    """Raised for protocol-level failures (not found, timeout, bad JSON)."""


@dataclass
class LspMessage:
    """Envelope we exchange over stdio."""

    payload: dict[str, Any]
    raw: bytes = b""


@dataclass
class LspClient:
    """Stdio JSON-RPC client for an LSP server.

    PURPOSE:      Launch the server, maintain the reader thread, send
                  requests / notifications, wait for responses.
    NOTES:        Thread-safe by design — the reader thread owns stdout
                  and feeds a queue keyed by request-id; callers block
                  on the queue with a timeout.
    """

    command: list[str]
    project_root: Path
    startup_timeout: float = 60.0
    request_timeout: float = 5.0
    _process: subprocess.Popen[bytes] | None = None
    _reader_thread: threading.Thread | None = None
    _pending: dict[int | str, queue.Queue[dict[str, Any]]] = field(default_factory=dict)
    _next_id: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stopped: threading.Event = field(default_factory=threading.Event)
    _notifications: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    _initialized: bool = False

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._process is not None:
            return
        if not shutil.which(self.command[0]):
            raise LspClientError(f"{self.command[0]} not on PATH")
        try:
            self._process = subprocess.Popen(  # noqa: S603 — subprocess is the whole point
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LspClientError(f"failed to spawn LSP server: {exc}") from exc
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="lsp-reader", daemon=True
        )
        self._reader_thread.start()

    def initialize(self) -> bool:
        """LSP initialize handshake. Returns True once `initialized` is sent."""
        if self._initialized:
            return True
        params: dict[str, Any] = {
            "processId": os.getpid(),
            "rootUri": f"file://{self.project_root}",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": False},
                    "definition": {"dynamicRegistration": False, "linkSupport": True},
                    "hover": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                },
                "workspace": {"workspaceFolders": True},
            },
            "workspaceFolders": [
                {"uri": f"file://{self.project_root}", "name": self.project_root.name}
            ],
        }
        try:
            self._request("initialize", params, timeout=self.startup_timeout)
        except LspClientError as exc:
            logger.debug("LSP initialize failed: %s", exc)
            return False
        self._notify("initialized", {})
        self._initialized = True
        return True

    def shutdown(self) -> None:
        if self._process is None:
            return
        try:
            self._request("shutdown", None, timeout=5.0)
            self._notify("exit", None)
        except LspClientError as exc:
            logger.debug("LSP shutdown race: %s", exc)
        self._stopped.set()
        try:
            self._process.terminate()
            self._process.wait(timeout=5.0)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("LSP terminate: %s", exc)
        finally:
            self._process = None
            self._initialized = False

    # -- Public API --------------------------------------------------------

    def did_open(self, file_path: Path, *, language_id: str = "python") -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("didOpen read failed for %s: %s", file_path, exc)
            return
        self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_path.resolve().as_uri(),
                    "languageId": language_id,
                    "version": 1,
                    "text": content,
                }
            },
        )

    def goto_definition(
        self, file_path: Path, line: int, character: int
    ) -> list[dict[str, Any]]:
        """Ask the server where `file_path:line:character` is defined.

        Returns a (possibly empty) list of Location / LocationLink dicts.
        """
        result = self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": file_path.resolve().as_uri()},
                "position": {"line": int(line), "character": int(character)},
            },
            timeout=self.request_timeout,
        )
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    # -- Internals ---------------------------------------------------------

    def _allocate_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    def _request(
        self,
        method: str,
        params: Any,
        *,
        timeout: float,
    ) -> Any:
        if self._process is None or self._process.stdin is None:
            raise LspClientError("LSP server is not running")
        request_id = self._allocate_id()
        inbox: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[request_id] = inbox
        try:
            self._send({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            })
            try:
                response = inbox.get(timeout=timeout)
            except queue.Empty as exc:
                raise LspClientError(
                    f"timeout waiting for {method} response"
                ) from exc
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            raise LspClientError(f"{method} failed: {response['error']}")
        return response.get("result")

    def _notify(self, method: str, params: Any) -> None:
        if self._process is None or self._process.stdin is None:
            raise LspClientError("LSP server is not running")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise LspClientError("LSP server stdin closed")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        try:
            self._process.stdin.write(header)
            self._process.stdin.write(body)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise LspClientError(f"LSP write failed: {exc}") from exc

    def _reader_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout
        while not self._stopped.is_set():
            header_bytes = b""
            while b"\r\n\r\n" not in header_bytes:
                chunk = stdout.readline()
                if not chunk:
                    return
                header_bytes += chunk
            header = header_bytes.decode("ascii", errors="replace")
            content_length = 0
            for line in header.splitlines():
                if line.lower().startswith("content-length:"):
                    try:
                        content_length = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        content_length = 0
            if content_length <= 0:
                continue
            body = b""
            while len(body) < content_length:
                block = stdout.read(content_length - len(body))
                if not block:
                    return
                body += block
            try:
                message = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.debug("LSP bad JSON: %s", exc)
                continue
            self._dispatch(message)

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            inbox = self._pending.get(message["id"])
            if inbox is not None:
                try:
                    inbox.put_nowait(message)
                except queue.Full:
                    logger.debug("LSP response inbox full for id=%s", message["id"])
            return
        try:
            self._notifications.put_nowait(message)
        except queue.Full:
            logger.debug("LSP notification queue full; dropping %s", message.get("method"))


__all__ = ["LspClient", "LspClientError"]
