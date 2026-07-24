import { useState, type ReactNode } from 'react';
import { apiGet } from '@/lib/api-client';
import { isPresenceAgent, useAgentCatalog } from './board-shared';
import type { AgentState } from './board-shared';
import { AgentBadge } from './AgentBadges';
import type { BoardListCard } from './types';

export function TopBar({
  taskCount,
  connected,
  agentStates,
  sessionCounts,
  legendOpen,
  streamOpen,
  showArchive,
  showSwimlanes,
  onToggleLegend,
  onToggleStream,
  onToggleArchive,
  onToggleSwimlanes,
  onToggleTweaks,
  onCreate,
  onOpenTask,
}: {
  taskCount: number;
  connected: boolean;
  agentStates: Record<string, AgentState>;
  sessionCounts?: Record<string, number>;
  legendOpen: boolean;
  streamOpen: boolean;
  showArchive: boolean;
  showSwimlanes: boolean;
  onToggleLegend: () => void;
  onToggleStream: () => void;
  onToggleArchive: () => void;
  onToggleSwimlanes: () => void;
  onToggleTweaks: () => void;
  onCreate: () => void;
  onOpenTask: (card: BoardListCard) => void;
}) {
  const agentRows = useAgentCatalog();
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 18px',
        borderBottom: '1px solid var(--col-border)',
        background:
          'linear-gradient(180deg, var(--board) 0%, color-mix(in srgb, var(--board) 92%, var(--board-grain)) 100%)',
        position: 'relative',
        zIndex: 10,
        flexWrap: 'wrap',
        minHeight: 48,
      }}
    >
      <div style={{ flex: 1 }} />

      {/* LIVE STATUS + ACTIONS */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
        <div
          title={`${taskCount} tasks · sse ${connected ? 'online' : 'offline'}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span style={{ color: 'var(--ink-faint)', fontSize: 13 }}>live:</span>
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
            {agentRows.filter(isPresenceAgent).map((a) => (
              <AgentBadge
                key={a.id}
                agentId={a.id}
                state={agentStates[a.id] ?? 'offline'}
                sessionCount={sessionCounts?.[a.id]}
              />
            ))}
          </div>
          <span
            style={{
              color: connected ? 'var(--cos-ok)' : 'var(--cos-faint)',
              fontSize: 13,
              fontWeight: 600,
              marginLeft: 4,
            }}
          >
            {connected ? 'sse' : 'off'}
          </span>
          <span style={{ color: 'var(--ink-faint)', fontSize: 13 }}>· {taskCount}</span>
        </div>

        <div style={{ width: 1, height: 22, background: 'var(--col-border)', margin: '0 2px' }} />

        <button
          type="button"
          onClick={onCreate}
          title="New task (n)"
          style={{
            padding: '6px 14px',
            fontSize: 11,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 700,
            background: 'var(--accent)',
            color: 'white',
            border: '1px solid var(--accent)',
            borderRadius: 4,
            cursor: 'pointer',
            letterSpacing: '.04em',
            boxShadow: '0 1px 2px rgba(217,108,44,.3)',
          }}
        >
          ＋ new
        </button>

        <SuggestNextButton onOpenTask={onOpenTask} />
        <TopBtn onClick={onToggleLegend} active={legendOpen}>⁂ legend</TopBtn>
        <TopBtn onClick={onToggleStream} active={streamOpen}>⎌ stream</TopBtn>
        <TopBtn onClick={onToggleSwimlanes} active={showSwimlanes}>
          {showSwimlanes ? '☰ swimlanes' : '▦ flat'}
        </TopBtn>
        <TopBtn onClick={onToggleArchive} active={showArchive}>
          {showArchive ? '▣ archive on' : '▢ archive'}
        </TopBtn>
        <TopBtn onClick={onToggleTweaks}>⚙ tweaks</TopBtn>
      </div>
    </div>
  );
}

export function SuggestNextButton({ onOpenTask }: { onOpenTask: (card: BoardListCard) => void }) {
  // Producer: GET /api/board/pick → {candidates: BoardListCard[], count}
  // (board.py::board_pick wrapping cos_task_pick — emergency first, then
  // ready icebox by priority). Zero UI consumers before TASK-322.
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<BoardListCard[] | null>(null);

  const fetchPick = async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      const [data] = await apiGet<{ candidates: BoardListCard[]; count: number }>(
        '/api/board/pick?max_candidates=5',
      );
      setCandidates(data.candidates);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'pick failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: 'relative' }}>
      <TopBtn onClick={() => (open ? setOpen(false) : void fetchPick())} active={open}>
        ◎ suggest next
      </TopBtn>
      {open && (
        <div
          role="listbox"
          aria-label="Suggested next tasks"
          style={{
            position: 'absolute',
            top: '110%',
            right: 0,
            zIndex: 60,
            width: 340,
            maxHeight: 320,
            overflow: 'auto',
            background: 'var(--board)',
            border: '1px solid var(--col-border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,.35)',
            padding: 6,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
          }}
        >
          {loading && <div style={{ padding: 8, color: 'var(--ink-faint)' }}>picking…</div>}
          {error && <div style={{ padding: 8, color: 'var(--cos-err)' }}>{error}</div>}
          {!loading && !error && candidates !== null && candidates.length === 0 && (
            <div style={{ padding: 8, color: 'var(--ink-faint)' }}>
              no pullable task — nothing in emergency or ready icebox
            </div>
          )}
          {!loading &&
            !error &&
            (candidates ?? []).map((card) => (
              <button
                key={card.id}
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  setOpen(false);
                  onOpenTask(card);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '7px 8px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer',
                  color: 'var(--ink)',
                }}
              >
                <span style={{ fontWeight: 700 }}>{card.id}</span>{' '}
                <span style={{ color: 'var(--ink-faint)' }}>
                  {card.priority}
                  {card.status === 'emergency' ? ' · emergency' : ' · ready'}
                </span>
                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {card.title}
                </div>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

export function TopBtn({
  children,
  onClick,
  active,
}: {
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '6px 10px',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        fontWeight: 600,
        background: active ? 'var(--accent)' : 'transparent',
        color: active ? 'white' : 'var(--ink)',
        border: `1.5px solid ${active ? 'var(--accent)' : 'var(--line-soft)'}`,
        borderRadius: 4,
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

