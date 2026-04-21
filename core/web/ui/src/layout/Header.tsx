import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Search, Sparkles } from 'lucide-react';
import { apiGet } from '@/lib/api-client';

// Header: logo, global search stub, AI panel toggle placeholder, live
// health status dot. Polls /health every 10s (per slice spec #9).
type HealthState = 'ok' | 'degraded' | 'down' | 'unknown';

export default function Header() {
  const [health, setHealth] = useState<HealthState>('unknown');

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const [data] = await apiGet<{ status: string }>('/health');
        if (!cancelled) {
          setHealth(data.status === 'ok' ? 'ok' : 'degraded');
        }
      } catch {
        if (!cancelled) setHealth('down');
      }
    };

    poll();
    const id = setInterval(poll, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const dotColor =
    health === 'ok'
      ? 'bg-emerald-400'
      : health === 'degraded'
        ? 'bg-amber-400'
        : health === 'down'
          ? 'bg-rose-500'
          : 'bg-slate-500';

  return (
    <header className="flex h-12 items-center gap-3 border-b border-[#2a2f39] bg-[#1b1f27] px-4">
      <Link to="/graph" className="flex items-center gap-2 text-sm font-semibold">
        <span className="inline-block h-3 w-3 rounded-sm bg-[#7fd4a0]" aria-hidden />
        coding-os
      </Link>
      <nav className="ml-6 flex-1">
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            const q = new FormData(e.currentTarget).get('q');
            if (typeof q === 'string' && q.trim()) {
              window.location.href = `/search?q=${encodeURIComponent(q.trim())}`;
            }
          }}
          className="flex max-w-xl items-center gap-2 rounded border border-[#2a2f39] bg-[#0e1116] px-2 py-1"
        >
          <Search size={14} className="text-[#9ea4ae]" aria-hidden />
          <input
            name="q"
            type="search"
            placeholder="Search memory, docs, graph…"
            aria-label="Unified search"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[#6c7280]"
          />
        </form>
      </nav>
      <button
        type="button"
        aria-label="AI panel (coming soon)"
        disabled
        className="flex items-center gap-1 rounded border border-[#2a2f39] px-2 py-1 text-xs text-[#9ea4ae] opacity-60"
      >
        <Sparkles size={14} aria-hidden /> AI
      </button>
      <div
        className="flex items-center gap-1 text-xs text-[#9ea4ae]"
        title={`backend: ${health}`}
      >
        <Activity size={14} aria-hidden />
        <span className={`inline-block h-2 w-2 rounded-full ${dotColor}`} aria-hidden />
        <span>{health}</span>
      </div>
    </header>
  );
}
