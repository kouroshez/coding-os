import { useState } from 'react';
import { FileText, History, ListTodo, MessageSquare, Plus, Search } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { EmptyState } from '@/layout/HubPrimitives';
import ChatList from '@/features/cognition/ChatList';
import ChatView from '@/features/cognition/ChatView';
import TraceTimeline from '@/features/cognition/TraceTimeline';
import NewChatForm from '@/features/cognition/NewChatForm';
import OnboardingCard from '@/features/cognition/OnboardingCard';

const ONBOARD_PROMPT =
  'Help me set up my product docs — interview me briefly, then draft the minimum docs under docs/.';

const SUGGESTIONS: { icon: typeof ListTodo; label: string; prompt: string; onboard?: boolean }[] = [
  { icon: ListTodo, label: 'Start a task', prompt: 'Help me start a new task: ' },
  { icon: History, label: 'Resume where we left off', prompt: 'Summarize where we left off and propose the next step.' },
  { icon: FileText, label: 'Onboard my product docs', prompt: ONBOARD_PROMPT, onboard: true },
  { icon: Search, label: 'Ask the codebase', prompt: 'Explain how ' },
];

/**
 * Chat-first project landing. Left: a persistent session rail (always visible,
 * even inside a conversation) with a "+ New chat" affordance. Right: the live
 * conversation (ChatView) when a session is in the URL, else a warm hero +
 * composer + suggestions. Handoff is in-place (same tab) so the index never
 * disappears. Chat is Claude-SDK-gated; an `unavailable` envelope degrades to
 * install guidance — never a raw error on the first screen.
 */
export default function ChatLanding() {
  const { slug, sessionId } = useParams<{ slug?: string; sessionId?: string }>();
  const navigate = useNavigate();
  const [onboardMode, setOnboardMode] = useState(false);
  const [seed, setSeed] = useState('');
  const [showTrace, setShowTrace] = useState(false);
  const base = slug ? `/p/${encodeURIComponent(slug)}/workspace/chat` : '/workspace/chat';
  const openSession = (sid: string) => navigate(`${base}/${encodeURIComponent(sid)}`);
  const project = slug ?? 'coding-os';

  // Shares ChatList's query key, so React Query dedupes this to one fetch.
  const { error } = useApiGet(['cognition-chats'], '/api/cognition/chats', { limit: 100 }, {
    refetchIntervalMs: 10_000,
  });
  const unavailable = (error as { category?: string } | null)?.category === 'unavailable';

  if (unavailable) {
    return (
      <div className="h-full overflow-auto p-8">
        <EmptyState icon={<MessageSquare size={28} />} title="Chat needs Claude Code">
          <p>The Claude Agent SDK isn’t available in this project yet, so chat sessions can’t run here.</p>
          <p className="mt-2">Connect Claude Code to this folder (install the Claude Agent SDK), then reload this page.</p>
        </EmptyState>
      </div>
    );
  }

  const newChat = () => {
    setOnboardMode(false);
    setSeed('');
    navigate(base);
  };

  return (
    <div className="grid h-full min-h-0" style={{ gridTemplateColumns: '300px 1fr' }}>
      <aside
        aria-label="Chat sessions"
        className="flex min-h-0 flex-col border-r border-[var(--cos-border)] bg-[var(--cos-panel)]"
      >
        <div className="flex shrink-0 items-center justify-between px-3 py-2.5">
          <span className="text-[11px] font-bold tracking-widest text-[var(--cos-muted)] uppercase">
            Chats
          </span>
          <button
            type="button"
            onClick={newChat}
            className="flex items-center gap-1 rounded-md border border-[var(--cos-border)] px-2 py-1 text-[11px] font-medium text-[var(--cos-text)] hover:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            <Plus size={12} aria-hidden /> New chat
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <ChatList selected={sessionId ?? null} onSelect={openSession} />
        </div>
      </aside>

      <section className="min-h-0 overflow-hidden">
        {sessionId ? (
          <div
            className="grid h-full min-h-0"
            style={{ gridTemplateColumns: showTrace ? 'minmax(0,1fr) 360px' : '1fr' }}
          >
            <div className="flex min-h-0 flex-col">
              <div className="flex shrink-0 items-center justify-end border-b border-[var(--cos-border)] px-3 py-1.5">
                <button
                  type="button"
                  onClick={() => setShowTrace((v) => !v)}
                  aria-pressed={showTrace}
                  className="rounded-md border border-[var(--cos-border)] px-2 py-1 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                >
                  {showTrace ? 'Hide trace' : 'Trace'}
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <ChatView sessionId={sessionId} />
              </div>
            </div>
            {showTrace && (
              <aside
                aria-label="Session trace"
                className="min-h-0 overflow-auto border-l border-[var(--cos-border)] bg-[var(--cos-panel)]"
              >
                <TraceTimeline sessionId={sessionId} />
              </aside>
            )}
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col overflow-auto">
            <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 pt-10">
              {!onboardMode && <OnboardingCard onStart={() => setOnboardMode(true)} />}
              <h1 className="text-center text-2xl font-semibold tracking-tight text-[var(--cos-text)]">
                What should we build in <span className="text-[var(--cos-accent)]">{project}</span>?
              </h1>
            </div>

            <NewChatForm
              key={`${onboardMode ? 'onboard' : 'chat'}:${seed}`}
              onComplete={openSession}
              initialRole={onboardMode ? 'onboarder' : ''}
              initialPrompt={onboardMode ? ONBOARD_PROMPT : seed}
              endpoint={onboardMode ? '/api/cognition/onboard' : '/api/cognition/chat'}
            />

            {!onboardMode && (
              <div className="mx-auto -mt-1 flex w-full max-w-2xl flex-col gap-0.5 px-6 pb-10">
                {SUGGESTIONS.map((s) => {
                  const Icon = s.icon;
                  return (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => (s.onboard ? setOnboardMode(true) : setSeed(s.prompt))}
                      className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] text-[var(--cos-muted)] hover:bg-white/[0.04] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                    >
                      <Icon size={15} aria-hidden className="text-[var(--cos-faint)]" />
                      {s.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
