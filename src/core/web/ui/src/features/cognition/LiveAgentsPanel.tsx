import type { ReactNode } from 'react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useApiGet } from '@/lib/hooks';
import { useScopedLink } from '@/lib/use-scoped-link';
import { useEventStream } from '@/lib/use-event-stream';
import { agentStatus, cognitionHref, gateMeta, modelLabel, type HubAgentsResponse, type PresenceAgent } from '@/lib/presence';
import AgentDetailModal from './AgentDetailModal';

const QUERY_KEY = ['presence-agents-home'];

/** Live-agents grid for the landing — one card per non-offline agent across
 *  ALL registered projects (GET /api/hub/agents, each card tagged with its
 *  owning project slug — TASK-437). Clicking a card opens a centered detail
 *  modal (not a navigate-away); an SSE tick invalidates the query so the grid
 *  stays live between polls (TASK-194 + Hub redesign). */
export default function LiveAgentsPanel() {
  const qc = useQueryClient();
  const { data } = useApiGet<HubAgentsResponse>(QUERY_KEY, '/api/hub/agents', undefined, {
    refetchIntervalMs: 4000,
  });
  useEventStream(['presence-updated', 'agent-activity'], () => {
    void qc.invalidateQueries({ queryKey: QUERY_KEY });
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Flatten the per-project groups into one grid; each agent keeps its own slug
  // (TASK-437 cross-project roster). Card key = slug:agent so two projects'
  // same-named agents (both "claude") never collide.
  const agents = (data?.projects ?? [])
    .flatMap((p) => p.agents)
    .filter((a) => a.state && a.state !== 'offline');
  const selected = agents.find((a) => `${a.slug}:${a.agent}` === selectedId) ?? null;

  if (agents.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-[11px] font-semibold tracking-widest text-[var(--cos-muted)] uppercase">
        Live agents
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => (
          <AgentCard
            key={`${a.slug}:${a.agent}`}
            agent={a}
            onOpen={() => setSelectedId(`${a.slug}:${a.agent}`)}
          />
        ))}
      </div>
      <AgentDetailModal agent={selected} onClose={() => setSelectedId(null)} />
    </section>
  );
}

function AgentCard({ agent, onOpen }: { agent: PresenceAgent; onOpen: () => void }) {
  const { slug } = useScopedLink();
  const status = agentStatus(agent.state);
  const gate = gateMeta(agent.gate);
  const chatHref = cognitionHref(agent.slug, slug, agent.sdk_uuid, 'chat');

  return (
    <div className="rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)] p-3.5 transition-colors hover:border-[var(--cos-accent)]">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open details for ${agent.agent}`}
        className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2 w-2 rounded-full ${status.pulse ? 'animate-pulse' : ''}`}
            style={{ background: status.dot }}
            aria-hidden
          />
          <span className="text-sm font-semibold capitalize text-[var(--cos-text)]">{agent.agent}</span>
          {agent.slug && (
            <span className="text-[10px] text-[var(--cos-faint)]">· {agent.slug}</span>
          )}
          <span className="ml-auto text-[10px] font-medium text-[var(--cos-muted)]">{status.label}</span>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <Chip>{modelLabel(agent.model)}</Chip>
          {gate && (
            <Chip color={gate.color}>
              {gate.level}
              {gate.dims ? ` · ${gate.dims}` : ''}
            </Chip>
          )}
          {agent.role && <Chip subtle>{agent.role}</Chip>}
        </div>
        {agent.task && (
          <p className="mt-2 truncate text-xs text-[var(--cos-muted)]">
            <span className="text-[var(--cos-faint)]">Task </span>
            {agent.task}
          </p>
        )}
      </button>
      <div className="mt-2 flex items-center gap-3 border-t border-[var(--cos-border)] pt-2 text-[11px]">
        <button type="button" onClick={onOpen} className="text-[var(--cos-muted)] hover:text-[var(--cos-text)]">
          Details
        </button>
        {chatHref && (
          <Link to={chatHref} className="ml-auto text-[var(--cos-accent)] hover:underline">
            Open chat →
          </Link>
        )}
      </div>
    </div>
  );
}

function Chip({ children, color, subtle }: { children: ReactNode; color?: string; subtle?: boolean }) {
  if (color) {
    return (
      <span
        className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium text-white"
        style={{ background: color }}
      >
        {children}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-full border border-[var(--cos-border)] px-2 py-0.5 text-[10px] font-medium ${
        subtle ? 'text-[var(--cos-muted)]' : 'text-[var(--cos-text)]'
      }`}
    >
      {children}
    </span>
  );
}
