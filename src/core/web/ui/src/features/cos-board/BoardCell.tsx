import { TaskStickyCard } from './TaskStickyCard';
import { COLUMN_RAIL_WIDTH } from './board-shared';
import type { Highlight } from './board-shared';
import type { BoardDnD } from './useBoardDnD';
import type { BoardListCard, BoardTweaks } from './types';

interface BoardCellProps {
  cards: BoardListCard[];
  laneId: string;
  colId: string;
  wipCap: number | null;
  rail: boolean;
  tweaks: BoardTweaks;
  highlight: Highlight | null;
  dnd: BoardDnD;
  paletteFor: (task: BoardListCard) => { color: string; accent: string };
  onOpenTask: (task: BoardListCard) => void;
}

/** One (lane × column) drop zone — shared by the swimlane grid and flat mode. */
export function BoardCell({
  cards,
  laneId,
  colId,
  wipCap,
  rail,
  tweaks,
  highlight,
  dnd,
  paletteFor,
  onOpenTask,
}: BoardCellProps) {
  const isTarget = dnd.dragTarget === `${laneId}:${colId}`;
  const violated = wipCap != null && cards.length > wipCap;
  // A rail carries no drop handlers on purpose: BoardGrid clears every rail the
  // moment a drag starts, so by the time a card is looking for a target this
  // column is already a full-width drop zone.
  if (rail) {
    return (
      <div
        aria-hidden
        style={{
          width: COLUMN_RAIL_WIDTH,
          minWidth: COLUMN_RAIL_WIDTH,
          flexShrink: 0,
          borderRight: '1px dashed var(--col-border)',
        }}
      />
    );
  }
  return (
    <div
      onDragOver={(e) => dnd.onDragOver(e, laneId, colId)}
      onDrop={(e) => void dnd.onDrop(e, laneId, colId)}
      style={{
        flex: '1 1 0',
        minWidth: 190,
        padding: tweaks.density === 'cozy' ? '10px 10px 8px' : '6px 7px 5px',
        borderRight: '1px dashed var(--col-border)',
        background: isTarget
          ? 'rgba(217, 108, 44, .08)'
          : violated
            ? 'rgba(192,57,43,.04)'
            : 'transparent',
        minHeight: 120,
        transition: 'background .1s ease',
      }}
    >
      {cards.map((task) => {
        const palette = paletteFor(task);
        return (
          <TaskStickyCard
            key={task.id}
            task={task}
            laneColor={palette.color}
            laneAccent={palette.accent}
            density={tweaks.density}
            quietMode={tweaks.quietMode}
            agentSurface={tweaks.agentSurface}
            highlight={highlight}
            draggingId={dnd.dragging?.id || ''}
            onDragStart={dnd.onDragStart}
            onDragEnd={dnd.onDragEnd}
            onOpen={onOpenTask}
          />
        );
      })}
      {cards.length === 0 && (
        <div
          style={{
            fontFamily: 'inherit',
            fontSize: 14,
            color: 'var(--ink-faint)',
            textAlign: 'center',
            padding: '20px 4px',
            opacity: 0.5,
          }}
        >
          — empty —
        </div>
      )}
    </div>
  );
}
