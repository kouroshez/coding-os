import { FormEvent, KeyboardEvent, useState } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';
import { csrfHeader, resolveApiUrl } from '@/lib/api-client';
import { useRoles } from './roles';
import ModelPicker from './ModelPicker';

interface Block {
  type?: string;
  text?: string;
}

export default function NewChatForm({
  onComplete,
  initialRole = '',
  initialPrompt = '',
  endpoint = '/api/cognition/chat',
}: {
  /** Called with the SDK-resolved session id once the first turn finishes
   *  streaming, so the parent can hand off to the rich ChatView in place. */
  onComplete?: (sessionId: string) => void;
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
  const roles = useRoles();

  const start = async (e?: FormEvent) => {
    e?.preventDefault();
    const p = prompt.trim();
    if (!p || streaming) return;
    setStreaming(true);
    setErr(null);
    setText('');
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
            if (ev === 'session' && payload.session_id) {
              capturedId = payload.session_id;
            }
            // Streamed frames carry `content[]`, GET transcripts carry `blocks[]`
            // — read content first so inline streaming text renders.
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
    // Hand off to the rich ChatView once the first turn finished streaming —
    // the stream is done, so unmounting cannot cancel the server-side SDK
    // query (navigating mid-stream WOULD cancel it). In-place, same tab — the
    // session sidebar stays visible (no new-tab handoff).
    if (!failed && capturedId && onComplete) onComplete(capturedId);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void start();
    }
  };

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
      {err && <p className="px-1 text-[12px] text-[#f85149]">{err}</p>}
      {(streaming || text) && (
        <div
          dir="auto"
          className="rounded-xl border border-[var(--cos-border)] bg-black/15 p-4 text-[13px] leading-relaxed whitespace-pre-wrap text-[var(--cos-text)]"
        >
          {text || <span className="text-[var(--cos-faint)]">thinking…</span>}
        </div>
      )}
    </div>
  );
}
