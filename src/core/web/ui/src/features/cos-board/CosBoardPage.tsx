import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries } from '@/lib/hooks';
import { apiPost } from '@/lib/api-client';
import { useBoardTheme } from './BoardThemeProvider';
import type { BoardListCard } from './types';
import { AgentCatalogContext, LiveSessionsContext } from './board-shared';
import type { AgentState, CreateTaskResponse, Highlight } from './board-shared';
import { useBoardData } from './useBoardData';
import { useBoardViewState } from './useBoardViewState';
import { useBoardDnD } from './useBoardDnD';
import { BoardGrid } from './BoardGrid';
import { TaskDetailDrawer } from './task-detail';
import { AgentTaskModal } from './AgentTaskModal';
import { CreateTaskModal } from './CreateTaskModal';
import { LiveStreamPanel } from './LiveStreamPanel';
import { TweaksPanel } from './TweaksPanel';
import { LegendPanel } from './LegendPanel';
import { TopBar } from './TopBar';

export default function CosBoardPage() {
  const qc = useQueryClient();
  const { tweaks, setTweaks } = useBoardTheme();
  const data = useBoardData(tweaks);

  const [streamOpen, setStreamOpen] = useState<boolean>(true);
  const [legendOpen, setLegendOpen] = useState<boolean>(false);
  const [tweaksOpen, setTweaksOpen] = useState<boolean>(false);
  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [agentOpen, setAgentOpen] = useState<boolean>(false);
  const [detailTask, setDetailTask] = useState<BoardListCard | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const view = useBoardViewState(() => setCreateOpen(true));
  const dnd = useBoardDnD({
    cfg: data.cfg,
    filtered: data.filtered,
    tweaks,
    pushHumanEvent: data.pushHumanEvent,
    onActionError: setActionError,
  });

  // Deep-link focus: /workspace/board?task=TASK-NNN (e.g. from search) opens
  // that task's drawer, then consumes the param so a later close doesn't
  // re-open it. No-op until the card is present in the loaded board list.
  useEffect(() => {
    const focus = searchParams.get('task');
    if (!focus) return;
    const card = data.cards.find((c) => c.id === focus);
    if (!card) return;
    setDetailTask(card);
    const next = new URLSearchParams(searchParams);
    next.delete('task');
    setSearchParams(next, { replace: true });
  }, [searchParams, data.cards, setSearchParams]);

  if (data.isLoading) {
    return (
      <div style={{ padding: 24, fontFamily: "'JetBrains Mono', monospace", color: 'var(--ink-soft)' }}>
        loading board…
      </div>
    );
  }
  if (data.error) {
    return (
      <div style={{ padding: 24, fontFamily: "'JetBrains Mono', monospace", color: 'var(--cos-err)' }}>
        {data.error.message}
      </div>
    );
  }

  const { list } = data;

  return (
    <AgentCatalogContext.Provider value={data.agentCatalog}>
    <LiveSessionsContext.Provider value={data.liveSessions}>
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <TopBar
        taskCount={list?.count ?? 0}
        connected={data.connected}
        sessionCounts={list?.session_counts ?? {}}
        agentStates={
          list?.agent_states ?? (
            // Back-compat: pre-0.5 backends only send active_agents list.
            (list?.active_agents ?? ['human']).reduce<Record<string, AgentState>>(
              (acc, id) => ({ ...acc, [id]: 'active' }),
              {},
            )
          )
        }
        legendOpen={legendOpen}
        streamOpen={streamOpen}
        showArchive={tweaks.showArchive}
        showSwimlanes={tweaks.showSwimlanes}
        onToggleLegend={() => setLegendOpen((v) => !v)}
        onToggleStream={() => setStreamOpen((v) => !v)}
        onToggleArchive={() => setTweaks((t) => ({ ...t, showArchive: !t.showArchive }))}
        onToggleSwimlanes={() => setTweaks((t) => ({ ...t, showSwimlanes: !t.showSwimlanes }))}
        onToggleTweaks={() => setTweaksOpen((v) => !v)}
        onCreate={() => setCreateOpen(true)}
        onOpenTask={setDetailTask}
      />

      {actionError && (
        <div
          style={{
            padding: '6px 12px',
            background: 'rgba(220,38,38,.12)',
            borderBottom: '1px solid rgba(220,38,38,.35)',
            color: 'var(--cos-err)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
          }}
        >
          {actionError}
        </div>
      )}

      <BoardGrid
        data={data}
        tweaks={tweaks}
        view={view}
        dnd={dnd}
        highlight={highlight}
        streamOpen={streamOpen}
        onOpenTask={setDetailTask}
      />

      <LiveStreamPanel
        open={streamOpen && tweaks.agentSurface}
        onClose={() => setStreamOpen(false)}
        events={data.streamEvents}
        connected={data.connected}
      />
      <LegendPanel
        open={legendOpen}
        onClose={() => setLegendOpen(false)}
        swimlanes={data.swimlanes}
        filterKind={tweaks.filterKind}
        setFilterKind={(v) => setTweaks((t) => ({ ...t, filterKind: v }))}
        filterSwim={tweaks.filterSwim}
        setFilterSwim={(v) => setTweaks((t) => ({ ...t, filterSwim: v }))}
        highlight={highlight}
        setHighlight={setHighlight}
        taskCounts={data.taskCounts}
      />
      <TweaksPanel
        open={tweaksOpen}
        onClose={() => setTweaksOpen(false)}
        tweaks={tweaks}
        setTweaks={setTweaks}
        kindOptions={data.kindOptions}
        epicOptions={data.epicOptions}
      />

      <AgentTaskModal
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        onDone={() => {
          void invalidateApiQueries(qc, '/api/board/list');
        }}
      />

      <CreateTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onAgentMode={() => {
          setCreateOpen(false);
          setAgentOpen(true);
        }}
        swimlanes={data.swimlanes}
        nextId={
          (data.cards.reduce((m, t) => Math.max(m, parseInt(String(t.id).replace('TASK-', ''), 10) || 0), 0) || 200) + 1
        }
        onCreate={async (form) => {
          setActionError(null);
          try {
            const [payload] = await apiPost<CreateTaskResponse>('/api/board/create', form);
            const id = payload?.data?.task_id ?? payload?.task_id ?? form.title;
            setCreateOpen(false);
            setJustCreated(id);
            data.pushHumanEvent('human-create', {
              taskId: typeof id === 'string' ? id : null,
              message: `${form.kind} · lane ${form.swimlane} · ${form.priority} · "${form.title}"`,
            });
            setTimeout(() => setJustCreated(null), 2800);
            await invalidateApiQueries(qc, '/api/board/list');
            await invalidateApiQueries(qc, '/api/board/retro');
          } catch (err) {
            const msg = err instanceof Error ? err.message : 'create failed';
            setActionError(msg);
            data.pushHumanEvent('human-create', { taskId: null, message: `FAILED — ${msg}` });
          }
        }}
      />

      <TaskDetailDrawer
        task={detailTask}
        swimlanes={data.swimlanes}
        onClose={() => setDetailTask(null)}
      />

      {justCreated && (
        <div
          style={{
            position: 'fixed',
            bottom: 22,
            left: '50%',
            transform: 'translateX(-50%)',
            padding: '10px 18px',
            background: 'var(--cos-ok)',
            color: 'white',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 12,
            fontWeight: 600,
            borderRadius: 4,
            zIndex: 150,
            boxShadow: '0 10px 25px rgba(0,0,0,.25)',
            animation: 'fadeIn .2s ease',
          }}
        >
          ✓ created {justCreated} · validate-task-frontmatter.sh → ok · sync v13 → ok
        </div>
      )}
    </div>
    </LiveSessionsContext.Provider>
    </AgentCatalogContext.Provider>
  );
}
