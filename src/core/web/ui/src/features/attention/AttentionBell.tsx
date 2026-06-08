import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { useEventStream } from '@/lib/use-event-stream';
import {
  ATTENTION_BASE_TITLE,
  formatTabTitle,
  setFaviconDot,
  summarizeStreamEvent,
} from '@/lib/attention';

const ATTENTION_EVENTS = ['dispatch-completed', 'agent-blocked', 'needs-input'] as const;
const FEED_CAP = 30;

interface FeedItem {
  id: number;
  label: string;
  ts: number;
}

/**
 * Header attention center (TASK-252). Surfaces agent activity when the human is
 * not looking: an unread count on the tab title + favicon + (opt-in) the
 * Notification API, plus an in-app activity feed. The count clears on refocus.
 */
export default function AttentionBell() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [notifyOn, setNotifyOn] = useState(false);
  const notifyRef = useRef(false);
  const idRef = useRef(0);
  notifyRef.current = notifyOn;

  useEventStream(ATTENTION_EVENTS, (type, data) => {
    const label = summarizeStreamEvent(type, data);
    idRef.current += 1;
    setItems((cur) => [{ id: idRef.current, label, ts: Date.now() }, ...cur].slice(0, FEED_CAP));
    // Only escalate (badge + OS notification) when the human is NOT looking.
    if (typeof document !== 'undefined' && document.hidden) {
      setUnread((n) => n + 1);
      if (
        notifyRef.current &&
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      ) {
        try {
          new Notification('Coding OS', { body: label });
        } catch {
          /* notification construction can throw in some embeddings — ignore */
        }
      }
    }
  });

  useEffect(() => {
    if (typeof document !== 'undefined') document.title = formatTabTitle(unread, ATTENTION_BASE_TITLE);
    setFaviconDot(unread > 0);
  }, [unread]);

  useEffect(() => {
    const clearOnVisible = () => {
      if (typeof document !== 'undefined' && !document.hidden) setUnread(0);
    };
    window.addEventListener('focus', clearOnVisible);
    document.addEventListener('visibilitychange', clearOnVisible);
    return () => {
      window.removeEventListener('focus', clearOnVisible);
      document.removeEventListener('visibilitychange', clearOnVisible);
    };
  }, []);

  const toggleNotify = async () => {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'granted') {
      setNotifyOn((v) => !v);
      return;
    }
    if (Notification.permission === 'default') {
      const p = await Notification.requestPermission();
      setNotifyOn(p === 'granted');
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          setUnread(0);
        }}
        aria-label={unread > 0 ? `Activity, ${unread} new` : 'Activity'}
        className="relative rounded p-1.5 text-[var(--cos-muted)] hover:bg-[var(--cos-grain)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--cos-accent)] px-1 text-[9px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-[150] mt-2 w-72 overflow-hidden rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-[var(--cos-border)] px-3 py-2">
            <span className="text-[11px] font-semibold tracking-wide text-[var(--cos-muted)] uppercase">
              Activity
            </span>
            <button
              type="button"
              onClick={toggleNotify}
              className="text-[10px] text-[var(--cos-accent)] hover:underline focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
            >
              {notifyOn ? 'Notifications on' : 'Enable notifications'}
            </button>
          </div>
          <div className="max-h-72 overflow-auto">
            {items.length === 0 ? (
              <p className="px-3 py-4 text-center text-[12px] text-[var(--cos-faint)]">
                No recent agent activity
              </p>
            ) : (
              items.map((it) => (
                <div
                  key={it.id}
                  dir="auto"
                  className="border-b border-[var(--cos-border)] px-3 py-2 text-[12px] text-[var(--cos-text)] last:border-b-0"
                >
                  {it.label}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
