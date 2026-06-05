import { useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Activity, Brain, Layers, MessageSquare } from 'lucide-react';
import TraceList from '@/features/cognition/TraceList';
import TraceTimeline from '@/features/cognition/TraceTimeline';
import CostPanel from '@/features/cognition/CostPanel';
import ChainPanel from '@/features/cognition/ChainPanel';
import ChatList from '@/features/cognition/ChatList';
import ChatView from '@/features/cognition/ChatView';
import HookStream from '@/features/observability/HookStream';
import RolesPage from '@/pages/RolesPage';

type ViewMode = 'live' | 'chat' | 'trace' | 'roles';

const VIEW_LABELS: Record<ViewMode, { Icon: typeof Activity; label: string; hint: string }> = {
  live: { Icon: Activity, label: 'Live', hint: 'real-time hook stream (SSE tail of .hooks.log)' },
  chat: { Icon: MessageSquare, label: 'Chats', hint: 'Claude SDK transcripts · resume · fork' },
  trace: { Icon: Brain, label: 'Traces', hint: 'cognition events (.coding-os/<agent>/traces)' },
  roles: { Icon: Layers, label: 'Roles', hint: 'formula registry · composed chain · evidence' },
};
const VIEW_ORDER: ViewMode[] = ['live', 'chat', 'trace', 'roles'];

export default function CognitionPage() {
  const { sessionId, slug } = useParams<{ sessionId?: string; slug?: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [agent, setAgent] = useState<string>('claude');

  const rawView = search.get('view');
  const view: ViewMode =
    rawView === 'chat' || rawView === 'live' || rawView === 'roles' ? rawView : 'trace';
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

  // Trace mode = 3 panes (list · timeline · chain+cost). Chat = 2 panes.
  // Live + Roles render their own internal layout — no aside.
  const layout = useMemo(() => {
    if (view === 'trace') return { gridTemplateColumns: '300px 1fr 360px' } as const;
    if (view === 'chat') return { gridTemplateColumns: '300px 1fr' } as const;
    return null;
  }, [view]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ViewToggle view={view} onChange={setView} />
      {view === 'trace' || view === 'chat' ? (
        <div className="grid min-h-0 flex-1" style={layout!}>
          <aside className="min-h-0 overflow-hidden border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
            {view === 'trace' ? (
              <TraceList selected={sessionId ?? null} onSelect={setSession} />
            ) : (
              <ChatList selected={sessionId ?? null} onSelect={(sid) => setSession(sid)} />
            )}
          </aside>
          <section className="min-h-0 overflow-hidden">
            {sessionId ? (
              view === 'trace' ? (
                <TraceTimeline sessionId={sessionId} />
              ) : (
                <ChatView sessionId={sessionId} />
              )
            ) : (
              <EmptyState view={view} />
            )}
          </section>
          {view === 'trace' && (
            <aside className="flex min-h-0 flex-col overflow-hidden border-l border-[var(--cos-border)] bg-[var(--cos-panel)]">
              <ChainPanel agent={agent} />
              <div className="flex-1 overflow-hidden">
                <CostPanel onPick={(sid) => setSession(sid)} />
              </div>
            </aside>
          )}
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
    <div className="flex shrink-0 items-center justify-between border-b border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-6 py-2.5 backdrop-blur-md">
      <div className="flex items-center gap-6">
        <span className="inline-flex items-center gap-2 text-[10px] font-bold tracking-widest text-[var(--cos-muted)] uppercase">
          <span className="h-2 w-2 rounded-full bg-[var(--cos-brand-tint)] shadow-[0_0_8px_rgba(217,70,239,0.7)] animate-pulse" />
          cognition hub
        </span>
        <div className="flex items-center gap-1 rounded-full border border-white/5 bg-black/15 p-1">
          {VIEW_ORDER.map((v) => {
            const { Icon, label } = VIEW_LABELS[v];
            const active = view === v;
            return (
              <button
                key={v}
                type="button"
                onClick={() => onChange(v)}
                aria-pressed={active}
                className={[
                  'inline-flex items-center gap-1.5 rounded-full px-4 py-1.25 text-[11px] font-bold tracking-wide uppercase transition-all duration-300 cursor-pointer',
                  active
                    ? 'bg-[var(--cos-accent)] text-white shadow-lg  border border-white/10'
                    : 'text-[var(--cos-muted)] hover:text-[var(--cos-text)] hover:bg-white/5 border border-transparent',
                ].join(' ')}
              >
                <Icon size={12} aria-hidden />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>
      <span className="text-[10px] font-medium tracking-wide text-[var(--cos-faint)] italic max-w-sm text-right leading-relaxed truncate">{VIEW_LABELS[view].hint}</span>
    </div>
  );
}

function EmptyState({ view }: { view: ViewMode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-[var(--cos-muted)]">
      <p>
        {view === 'chat'
          ? 'pick a chat session to view the transcript'
          : 'pick a session to view its timeline'}
      </p>
      {view === 'trace' && (
        <p className="text-[10px]">or browse cost &amp; chain on the right →</p>
      )}
    </div>
  );
}
