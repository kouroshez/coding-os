from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapters.codex import chat_provider


class Wrapped:
    def __init__(self, root):
        self.root = root


def _thread():
    user = SimpleNamespace(
        id="user-1",
        type="userMessage",
        content=[Wrapped(SimpleNamespace(type="text", text="Fix the Hub chat"))],
    )
    reasoning = SimpleNamespace(
        id="reason-1",
        type="reasoning",
        summary=["Inspecting the transcript route"],
        content=[],
    )
    command = SimpleNamespace(
        id="tool-1",
        type="commandExecution",
        command="pytest -q",
        aggregated_output="1 passed",
        exit_code=0,
    )
    assistant = SimpleNamespace(id="assistant-1", type="agentMessage", text="Implemented.")
    return SimpleNamespace(
        id="019fc9ac-216e-7211-a224-dad139ff5712",
        name="Codex Hub repair",
        preview="Fix the Hub chat",
        updated_at=1_785_798_603,
        created_at=1_785_795_053,
        cwd="/repo",
        git_info=SimpleNamespace(branch="main"),
        source=Wrapped("vscode"),
        status=Wrapped("active"),
        model_provider="openai",
        turns=[
            SimpleNamespace(
                items=[Wrapped(user), Wrapped(reasoning), Wrapped(command), Wrapped(assistant)]
            )
        ],
    )


@pytest.mark.asyncio
async def test_list_sessions_normalizes_codex_identity(monkeypatch):
    thread = _thread()

    class Client:
        async def thread_list(self, **kwargs):
            assert kwargs["cwd"] == "/repo"
            return SimpleNamespace(data=[thread])

    monkeypatch.setattr(chat_provider, "_CLIENT", Client())
    rows = await chat_provider.list_sessions("/repo", 10)
    assert rows[0]["session_id"] == thread.id
    assert rows[0]["agent"] == "codex"
    assert rows[0]["writable"] is False
    assert rows[0]["last_modified"] == thread.updated_at * 1000


@pytest.mark.asyncio
async def test_get_session_normalizes_text_reasoning_and_tools(monkeypatch):
    thread = _thread()

    class FakeAsyncThread:
        def __init__(self, client, thread_id):
            assert thread_id == thread.id

        async def read(self, include_turns=False):
            assert include_turns is True
            return SimpleNamespace(thread=thread)

    import openai_codex

    monkeypatch.setattr(openai_codex, "AsyncThread", FakeAsyncThread)
    monkeypatch.setattr(chat_provider, "_CLIENT", object())
    payload = await chat_provider.get_session(thread.id, "/repo", 100, 0)

    assert payload is not None
    assert payload["session"]["agent"] == "codex"
    assert payload["session"]["writable"] is False
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "assistant",
        "user",
        "assistant",
    ]
    assert payload["messages"][2]["blocks"][0]["type"] == "tool_use"
    assert payload["messages"][3]["blocks"][0]["type"] == "tool_result"
