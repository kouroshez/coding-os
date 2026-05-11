import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { resolveApiUrl } from '@/lib/api-client';

interface ContentBlock {
  type: string;
  text?: string;
  name?: string;
  input?: unknown;
  content?: unknown;
  is_error?: boolean;
  id?: string;
  tool_use_id?: string;
}

interface ChatMessage {
  uuid?: string;
  type?: string;
  role?: string;
  model?: string | null;
  stop_reason?: string | null;
  blocks: ContentBlock[];
  parent_tool_use_id?: string | null;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  } | null;
}

interface SessionMeta {
  session_id: string;
  summary?: string | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  last_modified?: number | null;
  file_size?: number | null;
  git_branch?: string | null;
  cwd?: string | null;
}

interface ChatPayload {
  session: SessionMeta;
  messages: ChatMessage[];
  count: number;
}

interface LiveEvent {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  ts: number;
}

// Logical turn — what the human actually sees as a single "exchange".
// Folds in:
//   - assistant text + thinking + tool_use blocks
//   - the tool_result echoes that follow as `role:user` messages
// Real human prompts (role:user with text/image blocks, no tool_result) are
// their own turn.
type Turn =
  | { kind: 'human'; uuid: string; blocks: ContentBlock[] }
  | {
      kind: 'assistant';
      uuid: string;
      messages: ChatMessage[];           // possibly multiple SDK messages
      toolResults: Map<string, ContentBlock>;  // keyed by tool_use_id
    };

function isToolResultOnly(m: ChatMessage): boolean {
  return (
    m.role === 'user' &&
    m.blocks.length > 0 &&
    m.blocks.every((b) => b.type === 'tool_result')
  );
}

function buildTurns(messages: ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const m of messages) {
    if (m.role === 'user' && !isToolResultOnly(m)) {
      turns.push({ kind: 'human', uuid: m.uuid ?? `h-${turns.length}`, blocks: m.blocks });
      continue;
    }
    if (isToolResultOnly(m)) {
      // Attach to the last assistant turn (or create one if none).
      let last = turns[turns.length - 1];
      if (!last || last.kind !== 'assistant') {
        last = { kind: 'assistant', uuid: m.uuid ?? `a-${turns.length}`, messages: [], toolResults: new Map() };
        turns.push(last);
      }
      for (const b of m.blocks) {
        if (b.type === 'tool_result' && b.tool_use_id) {
          last.toolResults.set(b.tool_use_id, b);
        }
      }
      continue;
    }
    if (m.role === 'assistant' || m.type === 'assistant') {
      // Coalesce consecutive assistant messages into one turn so the
      // bubble doesn't fragment around thinking → text → tool_use → text.
      const last = turns[turns.length - 1];
      if (last && last.kind === 'assistant') {
        last.messages.push(m);
      } else {
        turns.push({
          kind: 'assistant',
          uuid: m.uuid ?? `a-${turns.length}`,
          messages: [m],
          toolResults: new Map(),
        });
      }
      continue;
    }
    // Unknown role — render as raw assistant for visibility.
    turns.push({
      kind: 'assistant',
      uuid: m.uuid ?? `u-${turns.length}`,
      messages: [m],
      toolResults: new Map(),
    });
  }
  return turns;
}

export default function ChatView({ sessionId }: { sessionId: string }) {
  // Live transcript — re-pull every 2s while the view is mounted so the
  // Hub panel reflects the same conversation the Claude Code IDE shows
  // (it writes to ~/.claude/projects/<key>/<uuid>.jsonl as the agent
  // turns; we just tail).  refetchIntervalMs flows through to TanStack
  // Query's refetchInterval — paused automatically on tab/window blur.
  const { data, isLoading, error, refetch } = useApiGet<ChatPayload>(
    ['chat-messages', sessionId],
    `/api/cognition/chat/${encodeURIComponent(sessionId)}`,
    { limit: 1000 },
    { refetchIntervalMs: 2000 },
  );
  const [draft, setDraft] = useState('');
  const [fork, setFork] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [streamErr, setStreamErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLiveEvents([]);
    setStreaming(false);
    setStreamErr(null);
    setDraft('');
  }, [sessionId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [data?.count, liveEvents.length]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const turns = useMemo(() => buildTurns(data?.messages ?? []), [data?.messages]);

  const send = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      const prompt = draft.trim();
      if (!prompt || streaming) return;

      setStreaming(true);
      setStreamErr(null);
      setLiveEvents([{ id: `local-${Date.now()}`, kind: 'pending-user', payload: { text: prompt }, ts: Date.now() }]);
      setDraft('');

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(
          resolveApiUrl(`/api/cognition/chat/${encodeURIComponent(sessionId)}/send`),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            body: JSON.stringify({ prompt, fork }),
            signal: controller.signal,
          },
        );
        if (!res.ok || !res.body) {
          const txt = await res.text().catch(() => '');
          throw new Error(`stream HTTP ${res.status}: ${txt.slice(0, 200)}`);
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let counter = 0;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx = buffer.indexOf('\n\n');
          while (idx >= 0) {
            const frame = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const lines = frame.split('\n');
            let eventName = 'event';
            let dataStr = '';
            for (const l of lines) {
              if (l.startsWith('event:')) eventName = l.slice(6).trim();
              else if (l.startsWith('data:')) dataStr += l.slice(5).trim();
            }
            try {
              const payload = dataStr ? JSON.parse(dataStr) : {};
              counter += 1;
              setLiveEvents((cur) => [
                ...cur,
                { id: `live-${Date.now()}-${counter}`, kind: eventName, payload, ts: Date.now() },
              ]);
            } catch (parseErr) {
              setLiveEvents((cur) => [
                ...cur,
                {
                  id: `raw-${Date.now()}-${counter++}`,
                  kind: eventName,
                  payload: { raw: dataStr.slice(0, 500), parse_error: String(parseErr) },
                  ts: Date.now(),
                },
              ]);
            }
            idx = buffer.indexOf('\n\n');
          }
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') setStreamErr('cancelled');
        else setStreamErr((err as Error).message ?? 'stream failed');
      } finally {
        setStreaming(false);
        abortRef.current = null;
        await refetch();
      }
    },
    [draft, fork, sessionId, streaming, refetch],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  const session = data?.session;
  const titleLine = useMemo(() => {
    if (!session) return sessionId;
    return session.custom_title ?? session.summary ?? sessionId;
  }, [session, sessionId]);

  if (isLoading) return <p className="p-4 text-sm text-[var(--cos-muted)]">loading transcript…</p>;
  if (error)
    return (
      <p role="alert" className="p-4 text-sm text-rose-400">
        {error.message}
      </p>
    );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-2">
        <h2 className="text-sm font-semibold text-[var(--cos-text)]">{titleLine}</h2>
        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-[var(--cos-muted)]">
          <span className="font-mono">{sessionId}</span>
          {session?.git_branch && <span>· {session.git_branch}</span>}
          <span>· {turns.length} turn{turns.length === 1 ? '' : 's'}</span>
          <span>· {data?.count ?? 0} msg{data?.count === 1 ? '' : 's'}</span>
          <Link
            to={`/cognition/${encodeURIComponent(sessionId)}`}
            className="ml-auto text-[var(--cos-accent)] hover:underline"
            title="see cognition trace for this session"
          >
            see trace →
          </Link>
        </p>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-auto px-4 py-3 cos-scroll">
        {turns.map((t) =>
          t.kind === 'human' ? (
            <HumanTurn key={t.uuid} blocks={t.blocks} />
          ) : (
            <AssistantTurn key={t.uuid} messages={t.messages} toolResults={t.toolResults} />
          ),
        )}

        {liveEvents.length > 0 && (
          <div className="my-4 border-t border-dashed border-[var(--cos-accent)] pt-3">
            <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--cos-accent)]">
              live · {streaming ? 'streaming…' : 'completed'}
            </div>
            {liveEvents.map((e) => (
              <LiveEventRow key={e.id} event={e} />
            ))}
          </div>
        )}

        {streamErr && (
          <p role="alert" className="mt-3 text-xs text-rose-400">
            {streamErr}
          </p>
        )}
      </div>

      <form onSubmit={send} className="shrink-0 border-t border-[var(--cos-border)] bg-[var(--cos-panel)] p-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send(e as unknown as FormEvent);
            }
          }}
          placeholder="resume this session — type a message (⌘/Ctrl + Enter to send)"
          rows={3}
          aria-label="Send message"
          className="w-full resize-y rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-3 py-2 text-sm text-[var(--cos-text)] focus:border-[var(--cos-accent)] focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-[10px] text-[var(--cos-muted)]">
            <input type="checkbox" checked={fork} onChange={(e) => setFork(e.target.checked)} />
            fork (don't mutate this session)
          </label>
          <span className="text-[10px] text-[var(--cos-muted)]">
            spawns Claude CLI · resume={sessionId.slice(0, 8)}…
          </span>
          <div className="ml-auto flex items-center gap-2">
            {streaming && (
              <button
                type="button"
                onClick={cancel}
                className="rounded border border-rose-500/50 px-3 py-1 text-xs text-rose-400 hover:bg-rose-500/10"
              >
                cancel
              </button>
            )}
            <button
              type="submit"
              disabled={!draft.trim() || streaming}
              className={[
                'rounded border px-3 py-1 text-xs font-semibold transition-colors',
                streaming || !draft.trim()
                  ? 'cursor-not-allowed border-[var(--cos-border)] text-[var(--cos-muted)] opacity-50'
                  : 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20',
              ].join(' ')}
            >
              {streaming ? 'streaming…' : fork ? 'fork & send' : 'send'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Turn renderers
// ---------------------------------------------------------------------------

function HumanTurn({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="mb-3 flex flex-col items-end gap-1">
      <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">you</div>
      <div className="max-w-[88%] rounded-lg border border-[var(--cos-accent)]/40 bg-[var(--cos-accent)]/8 px-3 py-2 text-sm text-[var(--cos-text)]">
        {blocks.map((b, i) => (
          <TextOrImage key={i} block={b} />
        ))}
      </div>
    </div>
  );
}

function AssistantTurn({
  messages,
  toolResults,
}: {
  messages: ChatMessage[];
  toolResults: Map<string, ContentBlock>;
}) {
  // Build a flat block list across the coalesced messages so we can
  // render text and tool-call/result pairs in document order.
  const allBlocks = useMemo(
    () => messages.flatMap((m) => m.blocks ?? []),
    [messages],
  );

  // Pick the most informative header model — usually the last message.
  const lastWithModel = [...messages].reverse().find((m) => m.model);
  const totalOutputTokens = messages.reduce(
    (acc, m) => acc + (m.usage?.output_tokens ?? 0),
    0,
  );
  const totalInputTokens = messages.reduce(
    (acc, m) => acc + (m.usage?.input_tokens ?? 0),
    0,
  );

  const textBlocks = allBlocks.filter((b) => b.type === 'text' || b.type === 'thinking');
  const toolUses = allBlocks.filter((b) => b.type === 'tool_use');
  const otherBlocks = allBlocks.filter(
    (b) => b.type !== 'text' && b.type !== 'thinking' && b.type !== 'tool_use',
  );

  return (
    <div className="mb-4 flex flex-col items-start gap-1">
      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
        <span>assistant</span>
        {lastWithModel?.model && <span>· {lastWithModel.model}</span>}
        {(totalInputTokens > 0 || totalOutputTokens > 0) && (
          <span>· {totalInputTokens}+{totalOutputTokens} tok</span>
        )}
        {toolUses.length > 0 && (
          <span>· {toolUses.length} tool call{toolUses.length === 1 ? '' : 's'}</span>
        )}
      </div>
      <div className="max-w-[88%] space-y-1 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-sm text-[var(--cos-text)]">
        {textBlocks.length === 0 && toolUses.length === 0 && otherBlocks.length === 0 && (
          <p className="text-xs text-[var(--cos-muted)]">(empty message)</p>
        )}
        {textBlocks.map((b, i) => (
          <TextOrImage key={`t-${i}`} block={b} />
        ))}
        {toolUses.map((b, i) => (
          <ToolCall
            key={`tu-${i}`}
            toolUse={b}
            result={b.id ? toolResults.get(b.id) : undefined}
          />
        ))}
        {otherBlocks.map((b, i) => (
          <pre
            key={`o-${i}`}
            className="my-1 overflow-auto rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 text-[10px] text-[var(--cos-muted)] cos-scroll"
          >
            {JSON.stringify(b, null, 2)}
          </pre>
        ))}
      </div>
    </div>
  );
}

function TextOrImage({ block }: { block: ContentBlock }) {
  if (block.type === 'text') {
    if (!block.text) return null;
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-[var(--cos-text)]">
        {block.text}
      </pre>
    );
  }
  if (block.type === 'thinking') {
    if (!block.text) return null;
    return (
      <details className="my-1 rounded border border-dashed border-[var(--cos-border)] bg-[var(--cos-bg)]/50 text-[11px]">
        <summary className="cursor-pointer px-2 py-1 text-[var(--cos-muted)]">
          🧠 thinking ({block.text.length} chars)
        </summary>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words p-2 italic text-[var(--cos-muted)] cos-scroll">
          {block.text}
        </pre>
      </details>
    );
  }
  return null;
}

function ToolCall({
  toolUse,
  result,
}: {
  toolUse: ContentBlock;
  result?: ContentBlock;
}) {
  const hasError = result?.is_error;
  const resultText = useMemo(() => {
    if (!result) return null;
    const c = result.content;
    if (Array.isArray(c)) {
      return c.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('\n');
    }
    return typeof c === 'string' ? c : c == null ? '' : JSON.stringify(c, null, 2);
  }, [result]);

  return (
    <details
      className={[
        'my-1 rounded border text-[11px]',
        hasError
          ? 'border-rose-500/50 bg-rose-500/5'
          : 'border-[var(--cos-border)] bg-[var(--cos-bg)]',
      ].join(' ')}
    >
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-2 py-1 font-mono">
        <span className={hasError ? 'text-rose-400' : 'text-[var(--cos-accent)]'}>
          {hasError ? '⚠' : '🔧'} {toolUse.name ?? 'tool'}
        </span>
        <span className="text-[10px] text-[var(--cos-muted)]">
          {String(toolUse.id ?? '').slice(0, 8)}
        </span>
        {result ? (
          <span className={['ml-auto text-[10px]', hasError ? 'text-rose-400' : 'text-emerald-400'].join(' ')}>
            ↳ {hasError ? 'error' : 'result'}
          </span>
        ) : (
          <span className="ml-auto text-[10px] text-[var(--cos-faint)]">no result</span>
        )}
      </summary>
      <div className="space-y-1 border-t border-[var(--cos-border)] p-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">input</div>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--cos-panel)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll">
          {JSON.stringify(toolUse.input, null, 2)}
        </pre>
        {result && resultText != null && (
          <>
            <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
              result {hasError && <span className="text-rose-400">· error</span>}
            </div>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--cos-panel)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll">
              {resultText}
            </pre>
          </>
        )}
      </div>
    </details>
  );
}

function LiveEventRow({ event }: { event: LiveEvent }) {
  const { kind, payload } = event;

  if (kind === 'pending-user' && typeof payload.text === 'string') {
    return (
      <div className="mb-3 flex items-end justify-end">
        <div className="max-w-[88%] rounded-lg border border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 px-3 py-2 text-sm">
          <pre className="whitespace-pre-wrap break-words font-sans">{payload.text}</pre>
        </div>
      </div>
    );
  }

  if (kind === 'assistant') {
    const msg = (payload.message as Record<string, unknown> | undefined) ?? payload;
    const content = (msg?.content as unknown[] | undefined) ?? [];
    return (
      <div className="mb-3 flex flex-col items-start gap-1">
        <div className="text-[10px] uppercase tracking-wider text-[var(--cos-accent)]">assistant · live</div>
        <div className="max-w-[88%] space-y-1 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-sm text-[var(--cos-text)]">
          {Array.isArray(content) && content.length > 0 ? (
            content.map((c, i) => {
              const b = c as ContentBlock;
              if (b.type === 'text' || b.type === 'thinking') return <TextOrImage key={i} block={b} />;
              if (b.type === 'tool_use') return <ToolCall key={i} toolUse={b} />;
              return null;
            })
          ) : (
            <pre className="whitespace-pre-wrap break-words text-[10px] text-[var(--cos-muted)]">
              {JSON.stringify(payload, null, 2)}
            </pre>
          )}
        </div>
      </div>
    );
  }

  if (kind === 'result') {
    const cost = (payload as { total_cost_usd?: number }).total_cost_usd;
    const dur = (payload as { duration_ms?: number }).duration_ms;
    return (
      <div className="mb-3 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-300">
        ✓ result · {dur != null ? `${dur}ms` : ''} {cost != null ? `· $${cost.toFixed(4)}` : ''}
      </div>
    );
  }

  if (kind === 'error') {
    return (
      <div className="mb-3 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-300">
        ⚠ {String((payload as { message?: string }).message ?? JSON.stringify(payload))}
      </div>
    );
  }

  if (kind === 'started' || kind === 'done') {
    return (
      <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">{kind}</div>
    );
  }

  return (
    <details className="mb-2 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] text-[10px]">
      <summary className="cursor-pointer px-2 py-1 font-mono text-[var(--cos-muted)]">{kind}</summary>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words p-2 text-[var(--cos-text)] cos-scroll">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
