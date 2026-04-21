import { apiPost } from '@/lib/api-client';

export interface BoardCard {
  task_id: string;
  title: string;
  swimlane?: string;
  kind?: string;
  status: string;
  priority?: string;
}

// Drag-drop is out of scope for the scaffold per spec #5. A move menu
// triggers /api/board/move; the SSE stream updates the affected column.
export default function TaskCard({
  card,
  onMoved,
  lanes,
}: {
  card: BoardCard;
  onMoved: () => void;
  lanes: string[];
}) {
  const onMove = async (to: string) => {
    try {
      await apiPost('/api/board/move', { task_id: card.task_id, to });
      onMoved();
    } catch {
      // error surfaces via the next board-list re-render's error state
    }
  };

  return (
    <article className="rounded border border-[#2a2f39] bg-[#11151c] p-2 text-xs">
      <header className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-[#7fd4a0]">{card.task_id}</span>
        {card.priority && (
          <span className="rounded bg-[#2a2f39] px-1 text-[10px] text-[#9ea4ae]">
            {card.priority}
          </span>
        )}
      </header>
      <p className="mb-1 truncate" title={card.title}>
        {card.title}
      </p>
      <footer className="flex flex-wrap items-center gap-1 text-[10px] text-[#9ea4ae]">
        {card.swimlane && <span>{card.swimlane}</span>}
        {card.kind && <span>· {card.kind}</span>}
        <div className="ml-auto">
          <select
            aria-label={`Move ${card.task_id}`}
            value=""
            onChange={(e) => {
              if (e.target.value) onMove(e.target.value);
            }}
            className="rounded border border-[#2a2f39] bg-[#0e1116] px-1 py-0.5 text-[10px]"
          >
            <option value="" disabled>
              move…
            </option>
            {lanes
              .filter((l) => l !== card.status)
              .map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
          </select>
        </div>
      </footer>
    </article>
  );
}
