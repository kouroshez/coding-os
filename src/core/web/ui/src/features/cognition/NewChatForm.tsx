import { FormEvent, KeyboardEvent, useEffect, useState } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';
import { consumeSse, streamDeltaText, streamToolName } from '@/lib/chat-stream';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { useRoles } from './roles';
import ModelPicker from './ModelPicker';
import EffortPicker from './EffortPicker';
import { useChatStatusLabel } from './chat-status';

interface Block {
  type?: string;
  text?: string;
  name?: string;
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
  const [effort, setEffort] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  // Latest tool the agent is running — shown so a tool-heavy turn reads as
  // live progress, not a frozen "working…".
  const [activity, setActivity] = useState('');
  // Response model + token usage, surfaced live so the first turn carries the
  // same "assistant · model · tok" header as the persisted ChatView turn — no
  // styling pop-in when the turn hands off.
  const [respModel, setRespModel] = useState('');
  const [inTokens, setInTokens] = useState(0);
  const [outTokens, setOutTokens] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  // The submitted prompt. The moment it's set the composer is REPLACED by a live
  // conversation (user bubble + streaming reply) — so the chat "opens" instantly
  // instead of leaving the user staring at a "thinking…" box in the composer.
  const [sent, setSent] = useState<string | null>(null);
  const roles = useRoles();
  // Data-driven live label (adapter.yaml::chat_status) — tool verb when a tool
  // is active, else a rotating playful phrase.
  const status = useChatStatusLabel(model, activity, streaming);

  // Seed the composer when a suggestion / "New chat" changes the incoming
  // prompt — WITHOUT remounting (the parent no longer keys on the seed), so the
  // model / effort / role the user already picked survive a suggestion click.
  useEffect(() => {
    setPrompt(initialPrompt);
  }, [initialPrompt]);

  // A suggestion that carries a role (e.g. 'onboarder') seeds it the same way —
  // no remount, so the picked model / effort survive. The onboarder role also
  // routes the turn to the docs-confined /onboard endpoint (see start()).
  useEffect(() => {
    setRole(initialRole);
  }, [initialRole]);

  const start = async (e?: FormEvent) => {
    e?.preventDefault();
    const p = prompt.trim();
    if (!p || streaming) return;
    setStreaming(true);
    setErr(null);
    setText('');
    setActivity('');
    setRespModel('');
    setInTokens(0);
    setOutTokens(0);
    setSent(p);
    onActive?.(true);
    let capturedId: string | null = null;
    let failed = false;
    // True once a StreamEvent delta has painted text — tells us to IGNORE the
    // trailing complete AssistantMessage's text (it would duplicate the reply).
    let gotDelta = false;
    try {
      await consumeSse(
        // The onboarder role confines writes to docs/ via its own endpoint;
        // every other role rides the default chat endpoint with role in the body.
        role === 'onboarder' ? '/api/cognition/onboard' : endpoint,
        { prompt: p, role: role || null, model: model || null, effort: effort || null },
        (ev, payload) => {
          if (ev === 'session' && typeof payload.session_id === 'string') capturedId = payload.session_id;
          // Partial streaming (include_partial_messages): paint the answer
          // token-by-token from StreamEvent deltas.
          if (ev === 'streamevent') {
            const dt = streamDeltaText(payload);
            if (dt) {
              gotDelta = true;
              setText((cur) => cur + dt);
              setActivity('');
            }
            const tn = streamToolName(payload);
            if (tn) setActivity(tn);
            return;
          }
          // Complete frames carry `content[]` (stream) / `blocks[]` (GET). Their
          // text is a FALLBACK only — once deltas streamed it, re-adding here
          // would double the reply.
          const blocks: Block[] = payload.content ?? payload.blocks ?? [];
          if (!gotDelta) {
            const t = blocks
              .filter((b) => b?.type === 'text' && b.text)
              .map((b) => b.text)
              .join('');
            if (t) {
              setText((cur) => cur + t);
              setActivity('');
            }
            const tool = blocks.find((b) => b?.type === 'tool_use' && b.name);
            if (tool?.name) setActivity(tool.name);
          }
          // Model + usage live (matches the persisted assistant header). Assistant
          // frames carry message as an object; error frames carry it as a string.
          const msgObj = payload.message && typeof payload.message === 'object' ? payload.message : undefined;
          const respM = msgObj?.model ?? payload.model;
          if (typeof respM === 'string' && respM) setRespModel(respM);
          const usage = msgObj?.usage ?? payload.usage;
          if (usage?.input_tokens != null) setInTokens((c) => Math.max(c, usage.input_tokens ?? 0));
          if (usage?.output_tokens != null) setOutTokens((c) => Math.max(c, usage.output_tokens ?? 0));
          if (ev === 'error' && typeof payload.message === 'string') setErr(payload.message);
        },
      );
    } catch (e2) {
      failed = true;
      setErr((e2 as Error).message ?? 'failed to start session');
      // Never swallow — surface to the browser console so a broken stream is
      // observable in devtools, not silent.
      console.error('[hub-chat] first-turn stream failed:', e2, { capturedId });
    } finally {
      setStreaming(false);
    }
    if (capturedId && onComplete) {
      // The SDK minted a session — hand off to it even if the turn errored
      // midway. A created session must never be abandoned/"vanish": ChatView
      // shows whatever persisted and surfaces any error inline.
      onComplete(capturedId);
    } else if (failed) {
      // No session id ever arrived — the turn never really started (network /
      // CSRF). Return to the composer so the user can retry; `err` stays visible.
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

  // ── Live conversation (after send) — same bubble styling as the persisted
  //    ChatView turn (HumanTurn / AssistantTurn), so the first answer renders
  //    fully styled from the first token instead of "popping into style" only
  //    after the handoff to ChatView.
  if (sent) {
    return (
      <div className="flex w-full flex-col gap-5">
        <div className="flex flex-col items-end gap-1.5">
          <div className="pr-1 font-mono text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
            you
          </div>
          <div
            dir="auto"
            className="max-w-[88%] rounded-2xl border border-[var(--cos-accent)] bg-[var(--cos-accent)]/12 px-4 py-3 text-sm leading-relaxed text-[var(--cos-text)] shadow-sm"
          >
            {sent}
          </div>
        </div>
        <div className="flex flex-col items-start gap-1.5">
          <div className="flex flex-wrap items-center gap-2 pl-1 font-mono text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
            <span>assistant</span>
            {respModel && <span className="opacity-80">· {respModel}</span>}
            {(inTokens > 0 || outTokens > 0) && (
              <span className="opacity-80">· {inTokens}+{outTokens} tok</span>
            )}
          </div>
          <div
            dir="auto"
            className="max-w-[88%] space-y-1.5 rounded-2xl border border-[var(--cos-border)]/40 bg-[var(--cos-panel)]/80 px-4 py-3 text-sm leading-relaxed text-[var(--cos-text)] shadow-md shadow-black/10"
          >
            {text ? (
              <MarkdownBlock source={text} />
            ) : (
              <span className="inline-flex items-center gap-1.5 text-[var(--cos-faint)]">
                <Loader2 size={13} className="animate-spin" />
                {status}…
              </span>
            )}
            {streaming && text && (
              <span className="mt-1.5 inline-flex items-center gap-1.5 text-[11px] text-[var(--cos-faint)]">
                <Loader2 size={11} className="animate-spin" />
                {status}…
              </span>
            )}
            {err && <p className="mt-2 text-[12px] text-[#f85149]">{err}</p>}
          </div>
        </div>
      </div>
    );
  }

  // ── Composer (before send) ──────────────────────────────────────────────
  return (
    <div className="flex w-full flex-col gap-3">
      {err && (
        <p role="alert" className="px-1 text-[12px] text-[#f85149]">
          {err}
        </p>
      )}
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
            <EffortPicker model={model} value={effort} onChange={setEffort} />
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
