"""Tests for graph_os.lsp_client — wire-protocol + binary detection.

The full subprocess round-trip is exercised by the real pyright driver
in production. These tests cover the pieces we can exercise without a
real subprocess: message framing, id allocation, client-error surface,
and the `binary missing` path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from graph_os.lsp_client import LspClient, LspClientError


class TestLspClientProtocol:
    def test_binary_missing_raises(self, tmp_path):
        client = LspClient(command=["no-such-binary"], project_root=tmp_path)
        with patch("graph_os.lsp_client.shutil.which", return_value=None):
            with pytest.raises(LspClientError):
                client.start()

    def test_send_encodes_content_length_header(self, tmp_path, monkeypatch):
        """Framing: body must be prefixed with a correct Content-Length line."""
        client = LspClient(command=["x"], project_root=tmp_path)

        class _FakeStdin:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def write(self, data: bytes) -> int:
                self.writes.append(data)
                return len(data)

            def flush(self) -> None:
                pass

        class _FakeProc:
            stdin = _FakeStdin()
            stdout = None
            stderr = None

        client._process = _FakeProc()
        payload = {"jsonrpc": "2.0", "method": "ping", "params": {}}
        client._send(payload)
        concatenated = b"".join(_FakeProc.stdin.writes)
        assert b"Content-Length:" in concatenated
        length_line = concatenated.split(b"\r\n", 1)[0]
        length = int(length_line.split(b":")[1].strip())
        body = concatenated.split(b"\r\n\r\n", 1)[1]
        assert len(body) == length
        assert json.loads(body.decode("utf-8")) == payload

    def test_send_on_closed_pipe_raises(self, tmp_path):
        client = LspClient(command=["x"], project_root=tmp_path)
        with pytest.raises(LspClientError):
            client._send({"jsonrpc": "2.0", "method": "noop"})

    def test_id_allocation_is_monotonic(self, tmp_path):
        client = LspClient(command=["x"], project_root=tmp_path)
        ids = [client._allocate_id() for _ in range(5)]
        assert ids == [1, 2, 3, 4, 5]

    def test_dispatch_matches_response_to_inbox(self, tmp_path):
        import queue

        client = LspClient(command=["x"], project_root=tmp_path)
        inbox: queue.Queue = queue.Queue(maxsize=1)
        client._pending[42] = inbox
        response = {"jsonrpc": "2.0", "id": 42, "result": {"ok": True}}
        client._dispatch(response)
        assert inbox.get_nowait() == response

    def test_dispatch_notification_goes_to_notifications_queue(self, tmp_path):
        client = LspClient(command=["x"], project_root=tmp_path)
        notification = {"jsonrpc": "2.0", "method": "$/progress", "params": {}}
        client._dispatch(notification)
        assert client._notifications.get_nowait() == notification

    def test_request_without_running_server_raises(self, tmp_path):
        client = LspClient(command=["x"], project_root=tmp_path)
        with pytest.raises(LspClientError):
            client._request("initialize", {}, timeout=0.01)

    def test_shutdown_when_never_started_is_noop(self, tmp_path):
        client = LspClient(command=["x"], project_root=tmp_path)
        client.shutdown()  # must not raise
