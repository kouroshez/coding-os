import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Modal } from '@/components/Modal';
import { useScopedLink } from '@/lib/use-scoped-link';
import { agentStatus, cognitionHref, gateMeta, modelLabel, type PresenceAgent } from '@/lib/presence';

/**
 * Live per-agent detail — opened from the live-agents grid. Reads its agent
 * from the same (SSE-invalidated) presence query the grid uses, so the values
 * stay live while open. Built on the shared Modal primitive for a11y.
 */
export default function AgentDetailModal({
  agent,
  onClose,
}: {
  agent: PresenceAgent | null;
  onClose: () => void;
}) {
  const { slug } = useScopedLink();
  const status = agent ? agentStatus(agent.state) : null;
  const gate = agent ? gateMeta(agent.gate) : null;
  const chatHref = cognitionHref(agent?.slug, slug, agent?.sdk_uuid, 'chat');
  const traceHref = cognitionHref(agent?.slug, slug, agent?.session_id, 'trace');

  return (
    <Modal
      open={!!agent}
      onClose={onClose}
      size="md"
      title={
        agent ? (
          <span className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: status?.dot }} aria-hidden />
            <span className="capitalize">{agent.agent}</span>
            <span className="text-xs font-normal text-[var(--cos-muted)]">{status?.label}</span>
          </span>
        ) : (
          ''
        )
      }
      footer={
        agent ? (
          <div className="flex w-full items-center gap-2">
            {traceHref && (
              <Link
                to={traceHref}
                onClick={onClose}
                className="rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-xs font-medium text-[var(--cos-text)] hover:bg-white/5"
              >
                View traces
              </Link>
            )}
            <span className="flex-1" />
            {chatHref ? (
              <Link
                to={chatHref}
                onClick={onClose}
                className="inline-flex items-center gap-1.5 rounded-md bg-[var(--cos-accent-solid)] px-3 py-1.5 text-xs font-semibold text-white"
              >
                Open chat session
              </Link>
            ) : (
              <span className="text-xs text-[var(--cos-muted)]">No linked chat session</span>
            )}
          </div>
        ) : null
      }
    >
      {agent && (
        <dl className="space-y-3">
          <Field label="Model" value={modelLabel(agent.model)} />
          {gate && (
            <FieldNode label="Thinking depth">
              <span
                className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium text-white"
                style={{ background: gate.color }}
              >
                {gate.level}
                {gate.dims ? <span className="opacity-80">· {gate.dims} dims</span> : null}
              </span>
            </FieldNode>
          )}
          {agent.role && (
            <FieldNode label="Role">
              <RoleChain role={agent.role} chain={agent.chain ?? []} />
            </FieldNode>
          )}
          <FieldNode label="Context window">
            <ContextMeter pct={agent.context_pct ?? null} />
          </FieldNode>
          {agent.skill_active && <Field label="Active skill" value={agent.skill_active} />}
          {agent.task && <Field label="Current task" value={agent.task} />}
          <Field label="Session" value={agent.session_id ?? '—'} mono />
        </dl>
      )}
    </Modal>
  );
}

function FieldNode({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-xs text-[var(--cos-muted)]">{label}</dt>
      <dd className="min-w-0 text-right text-sm">{children}</dd>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <FieldNode label={label}>
      <span className={mono ? 'font-mono text-xs break-all text-[var(--cos-text)]' : 'text-[var(--cos-text)]'}>
        {value}
      </span>
    </FieldNode>
  );
}

function RoleChain({ role, chain }: { role: string; chain: string[] }) {
  const items = chain.length > 0 ? chain : [role];
  return (
    <span className="flex flex-wrap items-center justify-end gap-1">
      {items.map((r, i) => (
        <span key={`${r}-${i}`} className="flex items-center gap-1">
          <span className={r === role ? 'text-xs font-semibold text-[var(--cos-accent)]' : 'text-xs text-[var(--cos-muted)]'}>
            {r}
          </span>
          {i < items.length - 1 && <span className="text-[var(--cos-faint)]">→</span>}
        </span>
      ))}
    </span>
  );
}

function ContextMeter({ pct }: { pct: number | null }) {
  if (pct == null) {
    return (
      <span
        className="text-xs text-[var(--cos-muted)]"
        title="Context tracking needs COS_SNAPSHOT_TRANSCRIPT=1 (off by default for privacy)"
      >
        not tracked
      </span>
    );
  }
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <span className="flex items-center justify-end gap-2">
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--cos-border)]">
        <span
          className="block h-full rounded-full"
          style={{ width: `${clamped}%`, background: clamped > 85 ? '#ef4444' : 'var(--cos-accent)' }}
        />
      </span>
      <span className="text-xs text-[var(--cos-text)]">{Math.round(clamped)}%</span>
    </span>
  );
}
