import { FormEvent, useState } from 'react';
import { resolveApiUrl } from '@/lib/api-client';

// The 11 semantic roles (stable set; see src/core/thinking_os/agents/).
const ROLES = [
  'researcher',
  'analyst',
  'architect',
  'documenter',
  'implementer',
  'reviewer',
  'debugger',
  'security_auditor',
  'deployer',
  'observer',
  'refactorer',
];
const MODELS = [
  { id: '', label: 'default' },
  { id: 'claude-opus-4-8', label: 'Opus 4.8' },
  { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6' },
  { id: 'claude-haiku-4-5', label: 'Haiku 4.5' },
];

interface Block {
  type?: string;
  text?: string;
}

export default function NewChatForm() {
  const [prompt, setPrompt] = useState('');
  const [role, setRole] = useState('');
  const [model, setModel] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const openChat = (sid: string) => {
    const m = window.location.pathname.match(/^\/p\/[^/]+/);
    const prefix = m ? m[0] : '';
    window.open(`${prefix}/cognition/${encodeURIComponent(sid)}?view=chat`, '_blank', 'noopener');
  };

  const start = async (e: FormEvent) => {
    e.preventDefault();
    const p = prompt.trim();
    if (!p || streaming) return;
    setStreaming(true);
    setErr(null);
    setText('');
    setSessionId(null);
    try {
      const res = await fetch(resolveApiUrl('/api/cognition/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
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
            if (ev === 'session' && payload.session_id) setSessionId(payload.session_id);
            const blocks: Block[] = payload?.blocks ?? [];
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
      setErr((e2 as Error).message ?? 'failed to start session');
    } finally {
      setStreaming(false);
    }
  };

  const sel =
    'rounded border border-[var(--cos-border)] bg-black/20 px-2 py-1 text-[11px] text-[var(--cos-text)]';

  return (
    <div className="flex h-full w-full max-w-2xl flex-col gap-3 self-center p-6">
      <h2 className="text-xs font-bold tracking-widest text-[var(--cos-muted)] uppercase">
        New chat session
      </h2>
      <form onSubmit={start} className="flex flex-col gap-3">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Write your prompt… (Claude only)"
          rows={5}
          className="w-full resize-y rounded border border-[var(--cos-border)] bg-black/20 px-3 py-2 text-[13px] text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        />
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--cos-muted)]">
            role
            <select value={role} onChange={(e) => setRole(e.target.value)} className={sel}>
              <option value="">none</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--cos-muted)]">
            model
            <select value={model} onChange={(e) => setModel(e.target.value)} className={sel}>
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={streaming || !prompt.trim()}
            className="rounded bg-[var(--cos-accent)] px-4 py-1.5 text-[11px] font-bold tracking-wide text-white uppercase disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-white/40"
          >
            {streaming ? 'starting…' : 'start'}
          </button>
          {sessionId && (
            <button
              type="button"
              onClick={() => openChat(sessionId)}
              className="rounded border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-accent)]"
            >
              ↗ open chat
            </button>
          )}
        </div>
      </form>
      {err && <p className="text-[11px] text-[#f85149]">{err}</p>}
      {text && (
        <pre className="min-h-0 flex-1 overflow-auto rounded border border-[var(--cos-border)] bg-black/15 p-3 text-[12px] whitespace-pre-wrap text-[var(--cos-text)]">
          {text}
        </pre>
      )}
    </div>
  );
}
