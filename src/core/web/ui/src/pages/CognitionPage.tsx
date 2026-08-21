import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Activity, Brain, Layers } from 'lucide-react';
import TraceList from '@/features/cognition/TraceList';
import TraceTimeline from '@/features/cognition/TraceTimeline';
import CostPanel from '@/features/cognition/CostPanel';
import QuotaPanel from '@/features/cognition/QuotaPanel';
import ChainPanel from '@/features/cognition/ChainPanel';
import HookStream from '@/features/observability/HookStream';
import RolesPage from '@/pages/RolesPage';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';

type ViewMode = 'live' | 'trace' | 'roles';

const VIEW_LABELS: Record<ViewMode, { Icon: typeof Activity; label: string; hint: string }> = {
  live: { Icon: Activity, label: 'Live', hint: 'real-time hook stream (SSE tail of .hooks.log)' },
  trace: { Icon: Brain, label: 'Traces', hint: 'cognition events (.coding-os/<agent>/traces)' },
  roles: { Icon: Layers, label: 'Roles', hint: 'formula registry · composed chain · evidence' },
};
const VIEW_ORDER: ViewMode[] = ['live', 'trace', 'roles'];

export default function CognitionPage() {
  const { sessionId, slug } = useParams<{ sessionId?: string; slug?: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [agent, setAgent] = useState<string>('claude');

  const rawView = search.get('view');
  // Chat moved to the Workspace landing — redirect any legacy ?view=chat
  // deep-link (live-agents cards, task chat-ref, old bookmarks) there.
  useEffect(() => {
    if (rawView !== 'chat') return;
    const wsBase = slug ? `/p/${encodeURIComponent(slug)}/workspace/chat` : '/workspace/chat';
    navigate(sessionId ? `${wsBase}/${encodeURIComponent(sessionId)}` : wsBase, { replace: true });
  }, [rawView, sessionId, slug, navigate]);

  const view: ViewMode = rawView === 'live' || rawView === 'roles' ? rawView : 'trace';
  const setView = (next: ViewMode) => {
    const sp = new URLSearchParams(search);
    if (next === 'trace') sp.delete('view');
    else sp.set('view', next);
    setSearch(sp, { replace: true });
  };

  const sessionBase = slug ? `/p/${encodeURIComponent(slug)}/cognition` : '/cognition';
  const setSession = (sid: string, sessionAgent?: string) => {
    if (sessionAgent) setAgent(sessionAgent);
    const sp = new URLSearchParams(search);
    if (view !== 'trace') sp.set('view', view);
    navigate(`${sessionBase}/${encodeURIComponent(sid)}?${sp.toString()}`);
  };

  // Trace mode = 3 panes (list · timeline · chain+cost). Live + Roles render
  // their own internal layout — no aside.
  const layout = useMemo(
    () => (view === 'trace' ? ({ gridTemplateColumns: '300px 1fr 360px' } as const) : null),
    [view],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewToggle view={view} onChange={setView} />
      {view === 'trace' ? (
        <div className="grid min-h-0 flex-1" style={layout!}>
          <aside className="min-h-0 overflow-hidden border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
            <TraceList selected={sessionId ?? null} onSelect={setSession} />
          </aside>
          <section className="min-h-0 overflow-hidden">
            {sessionId ? <TraceTimeline sessionId={sessionId} /> : <EmptyState view={view} />}
          </section>
          <aside className="flex min-h-0 flex-col overflow-hidden border-l border-[var(--cos-border)] bg-[var(--cos-panel)]">
            <ChainPanel agent={agent} />
            <QuotaPanel />
            <div className="flex-1 overflow-hidden">
              <CostPanel onPick={(sid) => setSession(sid)} />
            </div>
          </aside>
        </div>
      ) : view === 'live' ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <HookStream />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden">
          <RolesPage />
        </div>
      )}
    </div>
  );
}

function ViewToggle({ view, onChange }: { view: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <SubNav
      tablist
      ariaLabel="Cognition views"
      left={
        <span className="inline-flex items-center gap-2 text-[10px] font-semibold tracking-widest text-[var(--cos-muted)] uppercase">
          <span className="h-2 w-2 rounded-full bg-[var(--cos-brand-tint)] shadow-[0_0_8px_rgba(217,70,239,0.7)] animate-pulse" />
          cognition hub
        </span>
      }
      right={
        <span className="block max-w-sm truncate text-[10px] font-medium leading-relaxed tracking-tight text-[var(--cos-faint)] italic">
          {VIEW_LABELS[view].hint}
        </span>
      }
    >
      {VIEW_ORDER.map((v) => {
        const { Icon, label } = VIEW_LABELS[v];
        const active = view === v;
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(v)}
            className={`${subNavTabClass(active)} cursor-pointer`}
          >
            <Icon size={14} aria-hidden />
            <span>{label}</span>
          </button>
        );
      })}
    </SubNav>
  );
}

function EmptyState({ view }: { view: ViewMode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-[var(--cos-muted)]">
      <p>pick a session to view its timeline</p>
      {view === 'trace' && (
        <p className="text-[10px]">or browse cost &amp; chain on the right →</p>
      )}
    </div>
  );
}
