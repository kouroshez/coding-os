import { useEffect, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApiGet } from '@/lib/hooks';
import TaskCard, { type BoardCard } from './TaskCard';
import { useBoardStream } from './useBoardStream';

interface BoardPayload {
  cards?: BoardCard[];
  grouped?: Record<string, BoardCard[]>;
  count?: number;
}

// Columns default to the Scrumban lanes noted in the slice spec;
// when the /api/board/list response exposes a "grouped" map with its
// own lanes, those override (so consumer projects with different
// swimlane configs don't force a UI change).
const DEFAULT_LANES = ['icebox', 'ready', 'in_progress', 'testing', 'done'] as const;

export default function KanbanBoard() {
  const { data, isLoading, error } = useApiGet<BoardPayload>(
    ['board-list'],
    '/api/board/list',
    { limit: 200 },
  );
  const { bump, connected } = useBoardStream();
  const qc = useQueryClient();

  useEffect(() => {
    if (bump > 0) qc.invalidateQueries({ queryKey: ['/api/board/list'] });
  }, [bump, qc]);

  const columns = useMemo(() => {
    if (!data) return [] as Array<{ lane: string; cards: BoardCard[] }>;
    const cards = data.cards ?? [];
    const laneSet = new Set<string>();
    for (const c of cards) laneSet.add(c.status);
    const ordered = [
      ...DEFAULT_LANES.filter((l) => laneSet.has(l)),
      ...[...laneSet].filter((l) => !DEFAULT_LANES.includes(l as (typeof DEFAULT_LANES)[number])),
    ];
    if (ordered.length === 0) ordered.push(...DEFAULT_LANES);
    return ordered.map((lane) => ({
      lane,
      cards: cards.filter((c) => c.status === lane),
    }));
  }, [data]);

  const allLanes = useMemo(() => columns.map((c) => c.lane), [columns]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-[#2a2f39] px-4 py-2 text-xs">
        <h1 className="font-semibold uppercase tracking-wide text-[#9ea4ae]">Board</h1>
        <span className="text-[#9ea4ae]">
          {connected ? 'live' : 'disconnected'} ·{' '}
          {data?.count != null ? `${data.count} tasks` : '—'}
        </span>
      </header>
      {isLoading && <p className="p-4 text-sm text-[#9ea4ae]">loading board…</p>}
      {error && (
        <p role="alert" className="p-4 text-sm text-rose-400">
          {error.message}
        </p>
      )}
      {!isLoading && !error && (
        <div className="flex flex-1 gap-3 overflow-auto p-3 cos-scroll">
          {columns.map(({ lane, cards }) => (
            <section
              key={lane}
              className="flex w-72 shrink-0 flex-col rounded border border-[#2a2f39] bg-[#151a22]"
            >
              <header className="flex items-center justify-between border-b border-[#2a2f39] px-2 py-1 text-xs">
                <h2 className="font-semibold uppercase tracking-wide text-[#9ea4ae]">
                  {lane}
                </h2>
                <span className="text-[#6c7280]">{cards.length}</span>
              </header>
              <div className="flex flex-1 flex-col gap-2 overflow-auto p-2 cos-scroll">
                {cards.map((card) => (
                  <TaskCard
                    key={card.task_id}
                    card={card}
                    lanes={allLanes}
                    onMoved={() =>
                      qc.invalidateQueries({ queryKey: ['/api/board/list'] })
                    }
                  />
                ))}
                {cards.length === 0 && (
                  <p className="p-2 text-center text-xs text-[#6c7280]">empty</p>
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
