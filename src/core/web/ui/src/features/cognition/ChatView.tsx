import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { consumeSse, streamDeltaText, streamToolName } from '@/lib/chat-stream';
import { reportClientError } from '@/lib/client-logger';
import { useScopedLink } from '@/lib/use-scoped-link';
import { buildTurns } from './chat-turns';
import type { ChatPayload, LiveEvent } from './chat-turns';
import { AssistantTurn, HumanTurn, LiveAssistant, LiveEventList, LiveEventRow } from './chat-turn-views';

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
                  : 'bg-[var(--cos-accent-solid)] text-white hover:shadow-lg hover:shadow-[var(--cos-accent)]/20 hover:-translate-y-px active:translate-y-0',
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

