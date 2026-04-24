import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TraceList from '@/features/cognition/TraceList';
import TraceTimeline from '@/features/cognition/TraceTimeline';

export default function CognitionPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const setSession = (sid: string) => {
    navigate(`/cognition/${encodeURIComponent(sid)}`);
  };

  useEffect(() => {
    // no-op placeholder so URL-directed deep links work
  }, [sessionId]);

  return (
    <div className="grid h-full" style={{ gridTemplateColumns: '280px 1fr' }}>
      <aside className="border-r border-[var(--cos-border)] bg-[var(--cos-panel)]">
        <TraceList selected={sessionId ?? null} onSelect={setSession} />
      </aside>
      <section className="overflow-hidden">
        {sessionId ? (
          <TraceTimeline sessionId={sessionId} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--cos-muted)]">
            pick a session to view its timeline
          </div>
        )}
      </section>
    </div>
  );
}
