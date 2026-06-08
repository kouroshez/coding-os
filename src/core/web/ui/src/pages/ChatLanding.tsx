import { useNavigate, useParams } from 'react-router-dom';
import ChatList from '@/features/cognition/ChatList';
import ChatView from '@/features/cognition/ChatView';
import NewChatForm from '@/features/cognition/NewChatForm';

/**
 * Chat-first project landing (replaces the Mission-Control dashboard).
 * Left: the session sidebar (reused ChatList). Right: the live conversation
 * (ChatView) when a session is in the URL, otherwise the greeting + composer.
 * The composer hands off in place once the first turn finishes streaming.
 */
export default function ChatLanding() {
  const { slug, sessionId } = useParams<{ slug?: string; sessionId?: string }>();
  const navigate = useNavigate();
  const base = slug ? `/p/${encodeURIComponent(slug)}/workspace/chat` : '/workspace/chat';
  const openSession = (sid: string) => navigate(`${base}/${encodeURIComponent(sid)}`);

  return (
    <div className="grid h-full min-h-0" style={{ gridTemplateColumns: '300px 1fr' }}>
      <aside className="min-h-0 overflow-hidden border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <ChatList selected={sessionId ?? null} onSelect={openSession} />
      </aside>
      <section className="min-h-0 overflow-hidden">
        {sessionId ? <ChatView sessionId={sessionId} /> : <NewChatForm onComplete={openSession} />}
      </section>
    </div>
  );
}
