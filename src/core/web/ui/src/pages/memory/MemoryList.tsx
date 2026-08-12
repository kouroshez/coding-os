import { useState } from 'react';
import { CfgButton, EmptyRow, SectionCard } from '@/features/config/shared';
import type { SourceGroup } from './memory-derive';
import { UNKNOWN_SOURCE, isStat, sourceCopy } from './memory-format';
import { LessonCard, StatCard } from './MemoryCards';

const PAGE = 15;

function SourceSection({ group }: { group: SourceGroup }) {
  const [expanded, setExpanded] = useState(false);
  const copy = sourceCopy(group.source === UNKNOWN_SOURCE ? null : group.source);
  const visible = expanded ? group.items : group.items.slice(0, PAGE);
  const hidden = group.items.length - visible.length;

  return (
    <SectionCard
      title={copy.label}
      subtitle={copy.blurb}
      count={group.items.length}
      action={
        group.items.length > PAGE ? (
          <CfgButton onClick={() => setExpanded((v) => !v)} ariaPressed={expanded}>
            {expanded ? 'Show fewer' : `Show all ${group.items.length}`}
          </CfgButton>
        ) : undefined
      }
    >
      {visible.map((p) => (isStat(p) ? <StatCard key={p.id} p={p} /> : <LessonCard key={p.id} p={p} />))}
      {hidden > 0 && (
        <EmptyRow>
          {hidden} more in this group —{' '}
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="underline decoration-dotted underline-offset-2 hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-focus)]"
          >
            show all
          </button>
        </EmptyRow>
      )}
    </SectionCard>
  );
}

// Grouped by source — where the lesson came from — because that is the only
// axis with real spread on this data (tier is "Forming" on nearly every row).
export function MemoryList({
  groups,
  filtered,
  onClear,
}: {
  groups: SourceGroup[];
  filtered: boolean;
  onClear: () => void;
}) {
  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-4 py-8 text-center text-[13px] text-[var(--cos-muted)]">
        {filtered ? (
          <>
            <p>No lesson matches these filters.</p>
            <div className="mt-3 flex justify-center">
              <CfgButton onClick={onClear}>Clear filters</CfgButton>
            </div>
          </>
        ) : (
          <p>Nothing to show yet.</p>
        )}
      </div>
    );
  }

  return (
    <div>
      {groups.map((group) => (
        <SourceSection key={group.source} group={group} />
      ))}
    </div>
  );
}
