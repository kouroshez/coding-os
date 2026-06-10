import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { consumeSse, streamDeltaText, streamToolName } from '@/lib/chat-stream';
import { reportClientError } from '@/lib/client-logger';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { useScopedLink } from '@/lib/use-scoped-link';

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

// A resumed terminal session bakes the transparency banner (the `🔔 ses=…`
// line) into its transcript, and the model echoes it on resume despite the
// Hub system prompt asking it not to (the few-shot history outweighs the
// instruction). Strip a leading banner line from assistant prose so the Hub
// chat stays clean (TASK-283). Assistant-scoped — human messages are untouched.
function stripLeadingBanner(text: string): string {
  return text.replace(/^\s*🔔[^\n]*\n+/, '');
}

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
    // Unknown role with no renderable blocks — system/result transcript
    // entries that would otherwise render as an empty assistant bubble
    // (TASK-283). Skip them; keep any that DO carry content for visibility.
    if (!m.blocks || m.blocks.length === 0) continue;
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
  const { scopedLink } = useScopedLink();
  // Live transcript — re-pull every 2s while the view is mounted so the
  // Hub panel reflects the same conversation the Claude Code IDE shows
  // (it writes to ~/.claude/projects/<key>/<uuid>.jsonl as the agent
  // turns; we just tail).  refetchIntervalMs flows through to TanStack
  // Query's refetchInterval — paused automatically on tab/window blur.
  const [streaming, setStreaming] = useState(false);
  const { data, isLoading, error, refetch } = useApiGet<ChatPayload>(
    ['chat-messages', sessionId],
    `/api/cognition/chat/${encodeURIComponent(sessionId)}`,
    { limit: 1000 },
    // Pause the 2s transcript poll while a reply streams: the SDK persists the
    // just-sent user turn immediately, so a mid-stream refetch rendered it
    // alongside the live pending-user echo → the message showed twice
    // (TASK-283). The live SSE covers updates; finally{} does one refetch after.
    { refetchIntervalMs: streaming ? 0 : 2000 },
  );
  const [draft, setDraft] = useState('');
  const [fork, setFork] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  // Assistant reply painted token-by-token from StreamEvent deltas (the trailing
  // complete AssistantMessage is then skipped to avoid a double render).
  const [liveText, setLiveText] = useState('');
  const [liveActivity, setLiveActivity] = useState('');
  const [streamErr, setStreamErr] = useState<string | null>(null);
  // After a grace window a persistent 404 is a real miss (not a flush race).
  const [slowSync, setSlowSync] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLiveEvents([]);
    setLiveText('');
    setLiveActivity('');
    setStreaming(false);
    setStreamErr(null);
    setDraft('');
  }, [sessionId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [data?.count, liveEvents.length, liveText]);

  // A just-minted session's transcript jsonl can lag the stream's session id by
  // a beat; the 2s refetch catches it. Only after ~12s of a persistent 404 do we
  // treat it as a genuine miss instead of an endless "syncing…".
  useEffect(() => {
    setSlowSync(false);
    const t = setTimeout(() => setSlowSync(true), 12000);
    return () => clearTimeout(t);
  }, [sessionId]);

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
      setLiveText('');
      setLiveActivity('');
      setDraft('');

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        let counter = 0;
        let accum = '';
        let sawDelta = false;
        await consumeSse(
          `/api/cognition/chat/${encodeURIComponent(sessionId)}/send`,
          { prompt, fork },
          (eventName, payload) => {
            // Partial streaming: paint the reply token-by-token from StreamEvent
            // deltas instead of dumping hundreds of raw frames into liveEvents.
            if (eventName === 'streamevent') {
              const dt = streamDeltaText(payload);
              if (dt) {
                sawDelta = true;
                accum += dt;
                setLiveText(accum);
                setLiveActivity('');
              }
              const tn = streamToolName(payload);
              if (tn) setLiveActivity(tn);
              return;
            }
            // The trailing complete AssistantMessage duplicates the streamed text
            // — drop it once deltas have arrived (tool-only turns keep it).
            if (eventName === 'assistant' && sawDelta) return;
            counter += 1;
            setLiveEvents((cur) => [
              ...cur,
              { id: `live-${Date.now()}-${counter}`, kind: eventName, payload, ts: Date.now() },
            ]);
          },
          controller.signal,
        );
      } catch (err) {
        if ((err as Error).name === 'AbortError') setStreamErr('cancelled');
        else {
          const msg = (err as Error).message ?? 'stream failed';
          setStreamErr(msg);
          reportClientError('chat: follow-up stream failed', { message: msg, sessionId });
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        // Refetch reloads the persisted Claude jsonl which now contains
        // the new turn.  Clear liveEvents AFTER the refetch resolves so
        // the SSE stream's pending-user echo + assistant pill don't
        // double-render alongside the just-persisted HumanTurn /
        // AssistantTurn.  Without this clear the user sees their prompt
        // and the reply printed twice (TASK 2026-05-20 UI audit).
        await refetch();
        setLiveEvents([]);
        setLiveText('');
        setLiveActivity('');
        setStreamErr(null);
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

  if (isLoading && !data) return <p className="p-4 text-sm text-[var(--cos-muted)]">loading transcript…</p>;
  // Show an error screen ONLY when there is no transcript to display. A 404 right
  // after navigating to a freshly-minted session = the SDK jsonl isn't queryable
  // yet; the 2s refetch catches it, so show "syncing…" rather than a hard error
  // that reads as "the session vanished". A transient refetch error while data IS
  // present keeps the data on screen. A 404 past the grace window is a real miss.
  if (error && !data) {
    const status = (error as { status?: number }).status;
    if (status === 404 && !slowSync) {
      return (
        <p className="p-4 text-sm text-[var(--cos-muted)]">
          syncing this session…{' '}
          <span className="text-[var(--cos-faint)]">(just created — one moment)</span>
        </p>
      );
    }
    return (
      <p role="alert" className="p-4 text-sm text-[var(--cos-err)]">
        {status === 404 ? `chat session not found: ${sessionId}` : error.message}
      </p>
    );
  }

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
            to={scopedLink('cognition', encodeURIComponent(sessionId))}
            className="ml-auto text-[var(--cos-accent)] hover:underline"
            title="see cognition trace for this session"
          >
            see trace →
          </Link>
        </p>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-auto px-4 py-3 cos-scroll">
        {/* Centered, width-capped column: an uncapped chat stretched bubbles to
            ~88% of a 3440px monitor (unreadable line length) and a wide tool
            output with no min-w-0 forced the whole message wider on expand
            (CSS min-width:auto > max-width). max-w-4xl + min-w-0 fix both. */}
        <div className="mx-auto flex w-full min-w-0 max-w-4xl flex-col">
        {turns.map((t) =>
          t.kind === 'human' ? (
            <HumanTurn key={t.uuid} blocks={t.blocks} />
          ) : (
            <AssistantTurn key={t.uuid} messages={t.messages} toolResults={t.toolResults} />
          ),
        )}

        {(liveEvents.length > 0 || liveText || streaming) && (
          <div className="my-4 border-t border-dashed border-[var(--cos-accent)] pt-3">
            <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--cos-accent)]">
              live · {streaming ? 'streaming…' : 'completed'}
            </div>
            {liveEvents
              .filter((e) => e.kind === 'pending-user')
              .map((e) => (
                <LiveEventRow key={e.id} event={e} />
              ))}
            {(liveText || streaming) && (
              <LiveAssistant text={liveText} activity={liveActivity} streaming={streaming} />
            )}
            <LiveEventList events={liveEvents.filter((e) => e.kind !== 'pending-user')} />
          </div>
        )}

        {streamErr && (
          <p role="alert" className="mt-3 text-xs text-[var(--cos-err)]">
            {streamErr}
          </p>
        )}
        </div>
      </div>

      <form onSubmit={send} className="shrink-0 border-t border-[var(--cos-border)]/40 bg-[var(--cos-panel)]/90 backdrop-blur-md p-4">
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
          className="w-full resize-y rounded-xl border border-[var(--cos-border)]/50 bg-[var(--cos-bg)]/80 px-4 py-3 text-sm text-[var(--cos-text)] transition-all placeholder:text-[var(--cos-muted)] focus:border-[var(--cos-accent)] focus:ring-1 focus:ring-[var(--cos-accent)]/30 focus:outline-none"
        />
        <div className="mt-2.5 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-[10px] text-[var(--cos-muted)] select-none cursor-pointer">
            <input type="checkbox" checked={fork} onChange={(e) => setFork(e.target.checked)} className="rounded border-[var(--cos-border)]/60 bg-[var(--cos-bg)] text-[var(--cos-accent)] focus:ring-0" />
            fork (don't mutate this session)
          </label>
          <span className="text-[10px] text-[var(--cos-muted)] font-mono">
            spawns Claude CLI · resume={sessionId.slice(0, 8)}…
          </span>
          <div className="ml-auto flex items-center gap-2">
            {streaming && (
              <button
                type="button"
                onClick={cancel}
                className="rounded-full border border-[var(--cos-err)] px-4 py-1.5 text-xs text-[var(--cos-err)] hover:bg-[var(--cos-err-tint)] transition-colors"
              >
                cancel
              </button>
            )}
            <button
              type="submit"
              disabled={!draft.trim() || streaming}
              className={[
                'rounded-full px-5 py-1.5 text-xs font-semibold transition-all duration-150',
                streaming || !draft.trim()
                  ? 'cursor-not-allowed border border-[var(--cos-border)]/40 text-[var(--cos-muted)] opacity-50'
                  : 'bg-[var(--cos-accent)] text-white hover:shadow-lg hover:shadow-[var(--cos-accent)]/20 hover:-translate-y-px active:translate-y-0',
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
    <div className="mb-4 flex min-w-0 flex-col items-end gap-1.5">
      <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)] pr-1 font-mono">you</div>
      <div className="max-w-[88%] rounded-2xl border border-[var(--cos-accent)] bg-gradient-to-br from-[var(--cos-brand-tint)] via-[var(--cos-brand-tint)] to-transparent dark:from-[var(--cos-brand-tint)] dark:via-[var(--cos-brand-tint)] dark:to-transparent backdrop-blur-md px-4 py-3 text-sm text-[var(--cos-text)] shadow-lg ">
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

  // A coalesced turn with zero renderable blocks (content-less system/result
  // messages) renders nothing rather than an empty bubble (TASK-283).
  if (allBlocks.length === 0) return null;

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

  // Document-order render — text, thinking, tool_use, and any other
  // block kinds appear in the EXACT order the SDK emitted them, so a
  // tool call mid-stream sits between the surrounding prose instead of
  // collapsing to the bottom.  Tool results are looked up by id from
  // the trailing tool_result message that immediately follows.
  const toolUseCount = allBlocks.filter((b) => b.type === 'tool_use').length;

  return (
    <div className="mb-5 flex min-w-0 flex-col items-start gap-1.5">
      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--cos-muted)] pl-1 font-mono">
        <span>assistant</span>
        {lastWithModel?.model && <span className="opacity-80">· {lastWithModel.model}</span>}
        {(totalInputTokens > 0 || totalOutputTokens > 0) && (
          <span className="opacity-80">· {totalInputTokens}+{totalOutputTokens} tok</span>
        )}
        {toolUseCount > 0 && (
          <span className="opacity-80">· {toolUseCount} tool call{toolUseCount === 1 ? '' : 's'}</span>
        )}
      </div>
      <div className="min-w-0 max-w-[88%] space-y-1.5 rounded-2xl border border-[var(--cos-border)]/40 bg-[var(--cos-panel)]/80 backdrop-blur-md px-4 py-3 text-sm text-[var(--cos-text)] shadow-md shadow-black/10">
        {allBlocks.map((b, i) => {
          if (b.type === 'text' || b.type === 'thinking') {
            const blk = b.type === 'text' && b.text ? { ...b, text: stripLeadingBanner(b.text) } : b;
            return <TextOrImage key={`b-${i}`} block={blk} />;
          }
          if (b.type === 'tool_use') {
            return (
              <ToolCall
                key={`b-${i}`}
                toolUse={b}
                result={b.id ? toolResults.get(b.id) : undefined}
              />
            );
          }
          return (
            <pre
              key={`b-${i}`}
              dir="ltr"
              className="my-1 overflow-auto rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 text-[10px] text-[var(--cos-muted)] cos-scroll"
            >
              {JSON.stringify(b, null, 2)}
            </pre>
          );
        })}
      </div>
    </div>
  );
}

function TextOrImage({ block }: { block: ContentBlock }) {
  if (block.type === 'text') {
    if (!block.text) return null;
    return <MarkdownBlock source={block.text} />;
  }
  if (block.type === 'thinking') {
    if (!block.text) return null;
    return (
      <details className="my-1 rounded border border-dashed border-[var(--cos-border)] bg-[var(--cos-bg)]/50 text-[11px]">
        <summary className="cursor-pointer px-2 py-1 text-[var(--cos-muted)]">
          🧠 thinking ({block.text.length} chars)
        </summary>
        <div className="max-h-64 overflow-auto p-2 italic cos-scroll">
          <MarkdownBlock source={block.text} className="text-[11px] text-[var(--cos-muted)]" />
        </div>
      </details>
    );
  }
  return null;
}

function looksLikeJson(text: string): boolean {
  const trimmed = text.trimStart();
  return trimmed.startsWith('{') || trimmed.startsWith('[');
}

function ToolResultBody({ text }: { text: string }) {
  if (!text.trim()) {
    return (
      <pre dir="ltr" className="rounded bg-[var(--cos-panel)] p-2 font-mono text-[10px] text-[var(--cos-muted)] cos-scroll">
        (empty)
      </pre>
    );
  }
  if (looksLikeJson(text)) {
    return (
      <pre
        dir="ltr"
        className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--cos-panel)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll"
      >
        {text}
      </pre>
    );
  }
  return (
    <div className="max-h-64 overflow-auto rounded bg-[var(--cos-panel)] p-2 cos-scroll">
      <MarkdownBlock source={text} className="text-[12px]" />
    </div>
  );
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
          ? 'border-[var(--cos-err)] bg-[var(--cos-err-tint)]'
          : 'border-[var(--cos-border)] bg-[var(--cos-bg)]',
      ].join(' ')}
    >
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-2 py-1 font-mono">
        <span className={hasError ? 'text-[var(--cos-err)]' : 'text-[var(--cos-accent)]'}>
          {hasError ? '⚠' : '🔧'} {toolUse.name ?? 'tool'}
        </span>
        <span className="text-[10px] text-[var(--cos-muted)]">
          {String(toolUse.id ?? '').slice(0, 8)}
        </span>
        {result ? (
          <span className={['ml-auto text-[10px]', hasError ? 'text-[var(--cos-err)]' : 'text-[var(--cos-ok)]'].join(' ')}>
            ↳ {hasError ? 'error' : 'result'}
          </span>
        ) : (
          <span className="ml-auto text-[10px] text-[var(--cos-faint)]">no result</span>
        )}
      </summary>
      <div className="space-y-1 border-t border-[var(--cos-border)] p-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">input</div>
        <pre
          dir="ltr"
          className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--cos-panel)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll"
        >
          {JSON.stringify(toolUse.input, null, 2)}
        </pre>
        {result && resultText != null && (
          <>
            <div className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
              result {hasError && <span className="text-[var(--cos-err)]">· error</span>}
            </div>
            <ToolResultBody text={resultText} />
          </>
        )}
      </div>
    </details>
  );
}

// Signal events render inline.  Anything else is "noise" — the SDK
// emits hookevent / system / ratelimitevent / cost_update / etc. per
// turn; rendering each as a full collapsible row buries the actual
// conversation under 20+ identical-looking blocks.  Matching the
// VSCode Claude plugin's UX, we hide noise behind a single subtle
// pill at the END of the stream — invisible during normal use,
// expandable when an operator wants to inspect raw SDK plumbing.
const SIGNAL_KINDS = new Set([
  'pending-user',
  'assistant',
  'result',
  'error',
  'started',
  'done',
]);

// The streaming assistant reply, painted from StreamEvent text deltas. Matches
// AssistantTurn's bubble so it doesn't restyle when the persisted turn replaces
// it on refetch. Tool calls aren't rendered here (only a "running …" hint) — the
// refetched turn shows them in full.
function LiveAssistant({
  text,
  activity,
  streaming,
}: {
  text: string;
  activity: string;
  streaming: boolean;
}) {
  return (
    <div className="mb-5 flex min-w-0 flex-col items-start gap-1.5">
      <div className="pl-1 font-mono text-[10px] uppercase tracking-wider text-[var(--cos-accent)]">
        assistant · live
      </div>
      <div className="min-w-0 max-w-[88%] space-y-1.5 rounded-2xl border border-[var(--cos-border)]/40 bg-[var(--cos-panel)]/80 px-4 py-3 text-sm text-[var(--cos-text)] shadow-md shadow-black/10">
        {text && <MarkdownBlock source={stripLeadingBanner(text)} />}
        {streaming && (
          <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--cos-faint)]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--cos-accent)]" aria-hidden />
            {activity || 'working'}…
          </span>
        )}
      </div>
    </div>
  );
}

function LiveEventList({ events }: { events: LiveEvent[] }) {
  const { signal, noise } = useMemo(() => {
    const signalEvents: LiveEvent[] = [];
    const noiseEvents: LiveEvent[] = [];
    for (const e of events) {
      if (SIGNAL_KINDS.has(e.kind)) signalEvents.push(e);
      else noiseEvents.push(e);
    }
    return { signal: signalEvents, noise: noiseEvents };
  }, [events]);

  return (
    <>
      {signal.map((e) => (
        <LiveEventRow key={e.id} event={e} />
      ))}
      {noise.length > 0 && <NoiseGroup events={noise} />}
    </>
  );
}

function NoiseGroup({ events }: { events: LiveEvent[] }) {
  const kinds = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events) counts[e.kind] = (counts[e.kind] ?? 0) + 1;
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => `${k}×${n}`)
      .join(' · ');
  }, [events]);
  return (
    <details className="mb-2 rounded border border-dashed border-[var(--cos-border)]/40 bg-transparent text-[10px]">
      <summary className="cursor-pointer px-2 py-1 font-mono text-[var(--cos-faint)]/70 hover:text-[var(--cos-muted)]">
        ⓘ raw SDK events ({events.length}) · {kinds}
      </summary>
      <div className="border-t border-[var(--cos-border)]/30 p-2">
        {events.map((e) => (
          <details
            key={e.id}
            className="mb-1 rounded border border-[var(--cos-border)]/30 bg-[var(--cos-bg)]/50"
          >
            <summary className="cursor-pointer px-2 py-1 font-mono text-[var(--cos-muted)]">
              {e.kind}
            </summary>
            <pre
              dir="ltr"
              className="max-h-48 overflow-auto whitespace-pre-wrap break-words p-2 text-[var(--cos-text)] cos-scroll"
            >
              {JSON.stringify(e.payload, null, 2)}
            </pre>
          </details>
        ))}
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
          <MarkdownBlock source={payload.text} />
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
              if (b.type === 'text' || b.type === 'thinking') {
                const blk = b.type === 'text' && b.text ? { ...b, text: stripLeadingBanner(b.text) } : b;
                return <TextOrImage key={i} block={blk} />;
              }
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
      <div className="mb-3 rounded border border-[var(--cos-ok)] bg-[var(--cos-ok-tint)] px-3 py-2 text-[11px] text-[var(--cos-ok)]">
        ✓ result · {dur != null ? `${dur}ms` : ''} {cost != null ? `· $${cost.toFixed(4)}` : ''}
      </div>
    );
  }

  if (kind === 'error') {
    return (
      <div className="mb-3 rounded border border-[var(--cos-err)] bg-[var(--cos-err-tint)] px-3 py-2 text-[11px] text-[var(--cos-err)]">
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
