import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { EmptyState } from '@/layout/HubPrimitives';
import ChatList from '@/features/cognition/ChatList';
import ChatView from '@/features/cognition/ChatView';
import NewChatForm from '@/features/cognition/NewChatForm';
import OnboardingCard from '@/features/cognition/OnboardingCard';

const ONBOARD_PROMPT =
  'Help me set up my product docs — interview me briefly, then draft the minimum docs under docs/.';

/**
 * Chat-first project landing (replaces the Mission-Control dashboard).
 * Left: the session sidebar (reused ChatList). Right: the live conversation
 * (ChatView) when a session is in the URL, otherwise the greeting + composer.
 * The composer hands off in place once the first turn finishes streaming.
 *
 * Dogfood: chat is Claude-SDK-gated. A scaffolded consumer without the SDK
 * now LANDS here, so the `unavailable` envelope must degrade to install
 * guidance — never a raw error on the first screen.
 */
export default function ChatLanding() {
  const { slug, sessionId } = useParams<{ slug?: string; sessionId?: string }>();
  const navigate = useNavigate();
  const [onboardMode, setOnboardMode] = useState(false);
  const base = slug ? `/p/${encodeURIComponent(slug)}/workspace/chat` : '/workspace/chat';
  const openSession = (sid: string) => navigate(`${base}/${encodeURIComponent(sid)}`);

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

  return (
    <div className="grid h-full min-h-0" style={{ gridTemplateColumns: '300px 1fr' }}>
      <aside className="min-h-0 overflow-hidden border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <ChatList selected={sessionId ?? null} onSelect={openSession} />
      </aside>
      <section className="min-h-0 overflow-hidden">
        {sessionId ? (
          <ChatView sessionId={sessionId} />
        ) : (
          <div className="flex h-full min-h-0 flex-col overflow-auto">
            {!onboardMode && <OnboardingCard onStart={() => setOnboardMode(true)} />}
            <NewChatForm
              key={onboardMode ? 'onboard' : 'chat'}
              onComplete={openSession}
              initialRole={onboardMode ? 'onboarder' : ''}
              initialPrompt={onboardMode ? ONBOARD_PROMPT : ''}
              endpoint={onboardMode ? '/api/cognition/onboard' : '/api/cognition/chat'}
            />
          </div>
        )}
      </section>
    </div>
  );
}
