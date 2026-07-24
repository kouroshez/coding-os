import { useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { ConfigRow, Pill, StateRow, TabIntro } from './shared';

interface HookRow {
  name: string;
  event: string;
  matcher?: string | null;
  category: string;
  phase?: string | null;
}

function CollapsibleSection({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: ReactNode;
  count: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <section className="mb-3 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      >
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--cos-text)]">
          <ChevronRight size={14} aria-hidden className={`transition-transform ${open ? 'rotate-90' : ''}`} />
          {title}
          <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-normal text-[var(--cos-muted)]">
            {count}
          </span>
        </h3>
      </button>
      {open && (
        <div className="divide-y divide-[var(--cos-border)] border-t border-[var(--cos-border)]">{children}</div>
      )}
    </section>
  );
}

const HOOK_CATEGORY_ORDER = ['safety', 'enforcement', 'task', 'observability', 'reminder', 'other'];

export function HooksTab() {
  const { data, isLoading, error } = useApiGet<{ hooks: HookRow[] }>(['config-hooks'], '/api/hooks/list');
  if (isLoading) return <StateRow>Loading hooks…</StateRow>;
  if (error) return <StateRow>Could not load hooks: {error.message}</StateRow>;
  const rows = data?.hooks ?? [];
  const byCategory = new Map<string, HookRow[]>();
  for (const h of rows) {
    const cat = h.category || 'other';
    const bucket = byCategory.get(cat) ?? [];
    bucket.push(h);
    byCategory.set(cat, bucket);
  }
  const categories = [...byCategory.keys()].sort((a, b) => {
    const rank = (c: string) => {
      const i = HOOK_CATEGORY_ORDER.indexOf(c);
      return i < 0 ? HOOK_CATEGORY_ORDER.length : i;
    };
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  return (
    <>
      <TabIntro>
        The hooks that steer the agent inside its guardrails — {rows.length} registered, grouped by role.
        These are DNA: read-only here (safety hooks can never be disabled).
      </TabIntro>
      {categories.map((cat) => (
        <CollapsibleSection
          key={cat}
          title={<span className="capitalize">{cat}</span>}
          count={byCategory.get(cat)!.length}
          defaultOpen={cat === 'safety'}
        >
          {byCategory.get(cat)!.map((h, i) => (
            <ConfigRow
              key={`${h.name}-${h.event ?? ''}-${i}`}
              title={h.name}
              badges={h.event ? <Pill tone="muted">{h.event}</Pill> : undefined}
              meta={
                <>
                  {h.matcher && (
                    <>
                      matcher <span className="font-mono">{h.matcher}</span>
                      {' · '}
                    </>
                  )}
                  phase {h.phase ?? '—'}
                </>
              }
            />
          ))}
        </CollapsibleSection>
      ))}
    </>
  );
}

