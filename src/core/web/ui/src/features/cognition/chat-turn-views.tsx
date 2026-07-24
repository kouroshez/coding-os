import { useMemo } from 'react';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { stripLeadingBanner } from './chat-turns';
import type { ChatMessage, ContentBlock, LiveEvent } from './chat-turns';

export function HumanTurn({ blocks }: { blocks: ContentBlock[] }) {
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

export function AssistantTurn({
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
export function LiveAssistant({
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

export function LiveEventList({ events }: { events: LiveEvent[] }) {
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

export function LiveEventRow({ event }: { event: LiveEvent }) {
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
