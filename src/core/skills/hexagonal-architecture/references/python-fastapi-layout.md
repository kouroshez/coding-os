# Hexagonal Layout — Python + FastAPI (AI Adapter)

For services where Python is the right choice (ML/AI inference, fast scripting, NumPy/PyTorch integration). Pattern: same as Go, but Python's typing requires Protocol (PEP 544) for ports, and FastAPI's `Depends` is the composition root for HTTP routes.

## Folder Tree

```
ai-adapter/
├── pyproject.toml
├── src/
│   └── ai_adapter/
│       ├── __init__.py
│       ├── domain/                     ← INNER — pure
│       │   ├── __init__.py
│       │   ├── conversation/
│       │   │   ├── __init__.py
│       │   │   ├── message.py          ← Message value object (immutable)
│       │   │   ├── conversation.py     ← Conversation entity
│       │   │   └── errors.py           ← ConversationFull, MessageInvalid
│       │   └── recommendation/
│       │       ├── __init__.py
│       │       ├── score.py
│       │       └── errors.py
│       │
│       ├── application/                ← USE CASES + PORTS
│       │   ├── __init__.py
│       │   ├── ports/
│       │   │   ├── __init__.py
│       │   │   ├── conversation_repo.py    ← Protocol
│       │   │   ├── llm_provider.py         ← Protocol (Anthropic/OpenAI/local)
│       │   │   ├── embedding_store.py      ← Protocol (Postgres pgvector / Pinecone / Qdrant)
│       │   │   ├── clock.py
│       │   │   ├── uuid_gen.py
│       │   │   └── unit_of_work.py
│       │   │
│       │   └── usecase/
│       │       ├── __init__.py
│       │       ├── send_message.py     ← Single use case = single class with execute()
│       │       ├── send_message_test.py
│       │       ├── recommend_next_lesson.py
│       │       └── summarize_chat.py
│       │
│       ├── infrastructure/              ← OUTBOUND ADAPTERS
│       │   ├── __init__.py
│       │   ├── postgres/
│       │   │   ├── __init__.py
│       │   │   ├── conversation_repo.py    ← implements ConversationRepository
│       │   │   ├── unit_of_work.py
│       │   │   └── migrations/
│       │   │       └── 001_init.sql
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── anthropic_provider.py   ← implements LLMProvider
│       │   │   └── openai_provider.py
│       │   ├── embeddings/
│       │   │   ├── __init__.py
│       │   │   └── pgvector_store.py
│       │   └── system/
│       │       ├── __init__.py
│       │       ├── clock.py
│       │       └── uuid_gen.py
│       │
│       ├── delivery/                    ← INBOUND ADAPTERS
│       │   ├── __init__.py
│       │   ├── http/                   ← FastAPI app
│       │   │   ├── __init__.py
│       │   │   ├── server.py           ← create_app() factory
│       │   │   ├── deps.py             ← dependency providers (composition)
│       │   │   ├── error_handlers.py
│       │   │   └── routers/
│       │   │       ├── conversation.py
│       │   │       └── recommendation.py
│       │   └── cli/
│       │       ├── __init__.py
│       │       └── replay.py           ← `python -m ai_adapter.delivery.cli.replay`
│       │
│       └── fakes/                       ← in-memory adapters for tests
│           ├── __init__.py
│           ├── conversation_repo.py
│           ├── llm_provider.py
│           ├── clock.py
│           └── uuid_gen.py
└── tests/
    └── integration/                     ← real-DB adapter tests (slow, few)
        └── test_postgres_conversation_repo.py
```

## Ports as Protocols (PEP 544)

Use `typing.Protocol` for ports — it's structural typing, no inheritance required. Adapters implement the protocol implicitly.

```python
# src/ai_adapter/application/ports/conversation_repo.py
from typing import Protocol

from ai_adapter.domain.conversation import Conversation, ConversationID


class ConversationRepository(Protocol):
    """Persist and retrieve conversations.

    All methods must be `async def` — the application layer is async-first
    so adapters that wrap blocking I/O (e.g. SQLAlchemy sync) MUST run in
    a thread pool internally rather than expose sync surface.
    """

    async def save(self, conversation: Conversation) -> None: ...
    async def get(self, conversation_id: ConversationID) -> Conversation | None: ...
    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Conversation]: ...
```

```python
# src/ai_adapter/application/ports/llm_provider.py
from dataclasses import dataclass
from typing import Protocol

from ai_adapter.domain.conversation import Message


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    messages: list[Message]
    max_tokens: int
    temperature: float = 0.7
    model_hint: str | None = None  # "fast" | "quality" — provider maps to actual ID


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str  # "stop" | "length" | "filter"


class LLMProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
    async def stream(self, request: GenerationRequest): ...  # AsyncIterator[str]
```

## Use Case — Async, Pure Application Logic

```python
# src/ai_adapter/application/usecase/send_message.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_adapter.domain.conversation import (
    Conversation,
    ConversationID,
    Message,
    Role,
)

if TYPE_CHECKING:
    from ai_adapter.application.ports.clock import Clock
    from ai_adapter.application.ports.conversation_repo import ConversationRepository
    from ai_adapter.application.ports.llm_provider import LLMProvider, GenerationRequest
    from ai_adapter.application.ports.unit_of_work import UnitOfWork
    from ai_adapter.application.ports.uuid_gen import UUIDGen


@dataclass(frozen=True, slots=True)
class SendMessageInput:
    conversation_id: ConversationID
    user_text: str
    model_hint: str | None = None


@dataclass(frozen=True, slots=True)
class SendMessageOutput:
    assistant_text: str
    conversation_id: ConversationID
    input_tokens: int
    output_tokens: int


class SendMessage:
    """Append a user message to a conversation and produce the assistant reply."""

    def __init__(
        self,
        conversations: ConversationRepository,
        llm: LLMProvider,
        uow: UnitOfWork,
        clock: Clock,
        uuid_gen: UUIDGen,
        max_message_chars: int = 4000,
    ) -> None:
        self._conversations = conversations
        self._llm = llm
        self._uow = uow
        self._clock = clock
        self._uuid_gen = uuid_gen
        self._max_message_chars = max_message_chars

    async def execute(self, input_: SendMessageInput) -> SendMessageOutput:
        conv = await self._conversations.get(input_.conversation_id)
        if conv is None:
            raise ConversationNotFound(input_.conversation_id)

        user_msg = Message(
            id=self._uuid_gen.new(),
            role=Role.USER,
            text=input_.user_text,
            created_at=self._clock.now(),
        )
        conv.append(user_msg, max_chars=self._max_message_chars)

        result = await self._llm.generate(
            GenerationRequest(
                messages=conv.messages,
                max_tokens=1024,
                model_hint=input_.model_hint,
            )
        )

        assistant_msg = Message(
            id=self._uuid_gen.new(),
            role=Role.ASSISTANT,
            text=result.text,
            created_at=self._clock.now(),
        )
        conv.append(assistant_msg)

        async with self._uow:
            await self._conversations.save(conv)

        return SendMessageOutput(
            assistant_text=result.text,
            conversation_id=conv.id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )


class ConversationNotFound(Exception):
    def __init__(self, cid: ConversationID) -> None:
        super().__init__(f"conversation not found: {cid}")
        self.conversation_id = cid
```

## FastAPI Inbound Adapter — `deps.py` Is the Composition Root

The trick: build the use case once at app startup, store on `app.state`, expose via `Depends`. Routes never import the adapter classes — only the use case and DTOs.

```python
# src/ai_adapter/delivery/http/deps.py
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI, Request

from ai_adapter.application.usecase.send_message import SendMessage
from ai_adapter.infrastructure.llm.anthropic_provider import AnthropicProvider
from ai_adapter.infrastructure.postgres.conversation_repo import (
    PostgresConversationRepository,
)
from ai_adapter.infrastructure.postgres.unit_of_work import PostgresUnitOfWork
from ai_adapter.infrastructure.system.clock import SystemClock
from ai_adapter.infrastructure.system.uuid_gen import RandomUUIDGen


async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the dependency graph once, tear down on shutdown."""
    cfg = app.state.config

    # Outbound adapters
    pool = await create_pg_pool(cfg.database_url)  # asyncpg
    conversations = PostgresConversationRepository(pool)
    llm = AnthropicProvider(api_key=cfg.anthropic_api_key, default_model=cfg.default_model)
    uow = PostgresUnitOfWork(pool)
    clock = SystemClock()
    uuid_gen = RandomUUIDGen()

    # Use cases
    app.state.send_message = SendMessage(
        conversations=conversations,
        llm=llm,
        uow=uow,
        clock=clock,
        uuid_gen=uuid_gen,
    )

    try:
        yield
    finally:
        await pool.close()


# Dependency providers — routes call `Depends(get_send_message)`
def get_send_message(request: Request) -> SendMessage:
    return request.app.state.send_message
```

```python
# src/ai_adapter/delivery/http/routers/conversation.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ai_adapter.application.usecase.send_message import (
    SendMessage,
    SendMessageInput,
)
from ai_adapter.delivery.http.deps import get_send_message
from ai_adapter.domain.conversation import ConversationID

router = APIRouter(prefix="/conversations", tags=["conversation"])


# Pydantic at the boundary — translates JSON to use case DTO. Pydantic
# does NOT cross into application/ — that layer uses plain dataclasses.
class SendMessageRequest(BaseModel):
    user_text: str = Field(min_length=1, max_length=4000)
    model_hint: str | None = Field(default=None, pattern="^(fast|quality)$")


class SendMessageResponse(BaseModel):
    assistant_text: str
    conversation_id: str
    usage: dict[str, int]


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    use_case: SendMessage = Depends(get_send_message),
) -> SendMessageResponse:
    try:
        cid = ConversationID(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        result = await use_case.execute(
            SendMessageInput(
                conversation_id=cid,
                user_text=body.user_text,
                model_hint=body.model_hint,
            )
        )
    except ConversationNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return SendMessageResponse(
        assistant_text=result.assistant_text,
        conversation_id=result.conversation_id,
        usage={
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    )
```

## Test — Pure Async Use Case Test

```python
# src/ai_adapter/application/usecase/send_message_test.py
from __future__ import annotations

import datetime as dt
from uuid import UUID

import pytest

from ai_adapter.application.usecase.send_message import (
    SendMessage,
    SendMessageInput,
)
from ai_adapter.domain.conversation import (
    Conversation,
    ConversationID,
    Message,
    Role,
)
from ai_adapter.fakes.clock import FrozenClock
from ai_adapter.fakes.conversation_repo import InMemoryConversationRepo
from ai_adapter.fakes.llm_provider import FakeLLMProvider
from ai_adapter.fakes.unit_of_work import NoopUnitOfWork
from ai_adapter.fakes.uuid_gen import SequentialUUIDGen


@pytest.mark.asyncio
async def test_send_message_appends_user_and_assistant_turns() -> None:
    cid = ConversationID("conv-1")
    repo = InMemoryConversationRepo()
    await repo.save(Conversation(id=cid, user_id="u1", messages=[]))
    llm = FakeLLMProvider(reply="Hello back!")
    clock = FrozenClock(dt.datetime(2026, 4, 26, 12, 0, tzinfo=dt.timezone.utc))
    uuid_gen = SequentialUUIDGen()

    uc = SendMessage(
        conversations=repo,
        llm=llm,
        uow=NoopUnitOfWork(),
        clock=clock,
        uuid_gen=uuid_gen,
    )

    result = await uc.execute(SendMessageInput(conversation_id=cid, user_text="Hi"))

    assert result.assistant_text == "Hello back!"
    saved = await repo.get(cid)
    assert [m.role for m in saved.messages] == [Role.USER, Role.ASSISTANT]
    assert saved.messages[0].text == "Hi"
    assert saved.messages[1].text == "Hello back!"
    assert llm.call_count == 1
```

No Postgres, no Anthropic API call, no FastAPI. ~5 ms per test. Hundreds of these run in seconds.

## Why Protocol Beats abc.ABC for Ports

```python
# This works — adapter implements the protocol structurally, no inheritance:
class PostgresConversationRepository:  # NOTE: no base class
    def __init__(self, pool: asyncpg.Pool) -> None: ...
    async def save(self, conversation: Conversation) -> None: ...
    async def get(self, conversation_id: ConversationID) -> Conversation | None: ...
    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Conversation]: ...

# mypy/pyright verifies it satisfies ConversationRepository at the call site:
def wire(repo: ConversationRepository) -> None: ...
wire(PostgresConversationRepository(pool))  # ✓ type-check passes
```

This avoids the inheritance gymnastics of `abc.ABC` + `@abstractmethod` and keeps adapters free of port imports — they only need to import the domain types.

## Anti-Patterns Specific to FastAPI

1. **Pydantic in domain layer** — domain entities are dataclasses, not Pydantic models. Pydantic = serialization, only at delivery boundary.
2. **`Depends` in use cases** — use cases take constructor-injected ports, not Depends. Depends is a delivery-layer concept.
3. **HTTPException in domain** — domain raises `ConversationNotFound`; the router maps it to 404.
4. **SQLAlchemy models = domain entities** — they are not. Map between ORM rows and domain entities at the repository boundary. Pay the mapping cost; it's worth it.

## Key References

- Cosmic Python (Percival & Gregory) — *Architecture Patterns with Python*, the canonical book on hexagonal in Python.
- FastAPI dependency injection: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- PEP 544 — Protocols: <https://peps.python.org/pep-0544/>
- pytest-asyncio — for async tests: <https://pytest-asyncio.readthedocs.io/>
