import { FormEvent, KeyboardEvent, useState } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';
import { csrfHeader, resolveApiUrl } from '@/lib/api-client';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { useRoles } from './roles';
import ModelPicker from './ModelPicker';

interface Block {
  type?: string;
  text?: string;
}

export default function NewChatForm({
  onComplete,
  onActive,
  initialRole = '',
  initialPrompt = '',
  endpoint = '/api/cognition/chat',
}: {
  /** Called with the SDK-resolved session id once the first turn finishes, so
   *  the parent hands off to the rich ChatView (persisted history + follow-ups). */
  onComplete?: (sessionId: string) => void;
  /** Fired true when a turn starts so the parent can hide the hero/suggestions;
   *  false if it failed before starting (composer is restored). */
  onActive?: (active: boolean) => void;
  /** Preselect a role (e.g. 'onboarder' for the docs-scoped setup flow). */
  initialRole?: string;
  /** Prefill the composer (e.g. the onboarding kickoff prompt). */
  initialPrompt?: string;
  /** Streaming endpoint — '/api/cognition/onboard' confines writes to docs/. */
  endpoint?: string;
} = {}) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [role, setRole] = useState(initialRole);
  const [model, setModel] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  const [err, setErr] = useState<string | null>(null);
  // The submitted prompt. The moment it's set the composer is REPLACED by a live
  // conversation (user bubble + streaming reply) — so the chat "opens" instantly
  // instead of leaving the user staring at a "thinking…" box in the composer.
  const [sent, setSent] = useState<string | null>(null);
  const roles = useRoles();

  const start = async (e?: FormEvent) => {
    e?.preventDefault();
    const p = prompt.trim();
    if (!p || streaming) return;
    setStreaming(true);
    setErr(null);
    setText('');
    setSent(p);
    onActive?.(true);
    let capturedId: string | null = null;
    let failed = false;
    try {
      const res = await fetch(resolveApiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...csrfHeader() },
        body: JSON.stringify({ prompt: p, role: role || null, model: model || null }),
      });
      if (!res.ok || !res.body) {
        const t = await res.text().catch(() => '');
        let msg = `HTTP ${res.status}`;
        try {
          msg = JSON.parse(t)?.error?.message ?? msg;
        } catch {
          msg = t.slice(0, 160) || msg;
        }
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx = buffer.indexOf('\n\n');
        while (idx >= 0) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          let ev = 'event';
          let data = '';
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) ev = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          try {
            const payload = data ? JSON.parse(data) : {};
            if (ev === 'session' && payload.session_id) capturedId = payload.session_id;
            // Streamed frames carry `content[]`, GET transcripts carry `blocks[]`.
            const blocks: Block[] = payload?.content ?? payload?.blocks ?? [];
            const t = blocks
              .filter((b) => b?.type === 'text' && b.text)
              .map((b) => b.text)
              .join('');
            if (t) setText((cur) => cur + t);
            if (ev === 'error' && payload?.message) setErr(payload.message);
          } catch {
            /* skip unparseable frame */
          }
          idx = buffer.indexOf('\n\n');
        }
      }
    } catch (e2) {
      failed = true;
      setErr((e2 as Error).message ?? 'failed to start session');
    } finally {
      setStreaming(false);
    }
    if (!failed && capturedId && onComplete) {
      // Turn done — hand off to the rich ChatView (persisted history + the
      // follow-up composer) under the real session URL.
      onComplete(capturedId);
    } else if (failed && !capturedId) {
      // Never started (e.g. network/CSRF) — return to the composer to retry.
      setSent(null);
      onActive?.(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void start();
    }
  };

  // ── Live conversation (after send) ──────────────────────────────────────
  if (sent) {
    return (
      <div className="flex w-full flex-col gap-4">
        <div
          dir="auto"
          className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-[var(--cos-accent)]/15 px-4 py-2.5 text-[14px] leading-relaxed text-[var(--cos-text)]"
        >
          {sent}
        </div>
        <div dir="auto" className="max-w-[92%] text-[14px] leading-relaxed text-[var(--cos-text)]">
          {text ? (
            <MarkdownBlock source={text} />
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[var(--cos-faint)]">
              <Loader2 size={13} className="animate-spin" /> thinking…
            </span>
          )}
          {err && <p className="mt-2 text-[12px] text-[#f85149]">{err}</p>}
        </div>
      </div>
    );
  }

  // ── Composer (before send) ──────────────────────────────────────────────
  return (
    <div className="flex w-full flex-col gap-3">
      <form onSubmit={start}>
        <div className="rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)] p-4 shadow-sm transition focus-within:border-[var(--cos-accent)]/60 focus-within:ring-2 focus-within:ring-[var(--cos-accent)]/30">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Describe a task, or ask anything…"
            aria-label="Chat prompt"
            dir="auto"
            rows={4}
            className="min-h-[132px] w-full resize-none bg-transparent px-1 text-[15px] leading-relaxed text-[var(--cos-text)] placeholder:text-[var(--cos-faint)] focus:outline-none"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <ModelPicker value={model} onChange={setModel} />
            <label className="flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] bg-black/20 px-2.5 py-1 text-[11px] text-[var(--cos-muted)]">
              <span>role</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                aria-label="Agent role"
                className="bg-transparent text-[var(--cos-text)] focus:outline-none"
              >
                <option value="">none</option>
                {roles.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={streaming || !prompt.trim()}
              aria-label="Send"
              title="Send  (Enter)"
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-[var(--cos-accent)] text-white transition disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-white/40"
            >
              {streaming ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={16} />}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
