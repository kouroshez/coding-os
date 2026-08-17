import { type CSSProperties } from 'react';
import { COLUMN_RAIL_WIDTH, alpha, columnWipCap, lanePalette } from './board-shared';
import type { Highlight } from './board-shared';
import { SwimlaneLabel } from './TaskStickyCard';
import { ZoomControls } from './ZoomControls';
import { BoardCell } from './BoardCell';
import { BoardColumnHeaders } from './BoardColumnHeaders';
import type { BoardData } from './useBoardData';
import type { BoardDnD } from './useBoardDnD';
import type { BoardViewState } from './useBoardViewState';
import type { BoardListCard, BoardTweaks, SwimlaneDTO } from './types';

interface BoardGridProps {
  data: BoardData;
  tweaks: BoardTweaks;
  view: BoardViewState;
  dnd: BoardDnD;
  highlight: Highlight | null;
  streamOpen: boolean;
  onOpenTask: (task: BoardListCard) => void;
}

const NEUTRAL_PALETTE = { color: 'var(--ink-soft)', accent: 'var(--ink-soft)' };

const NO_RAILS: ReadonlySet<string> = new Set();
const LANE_LABEL_WIDTH = 130;
const COLUMN_WIDTH = 200;

function CollapsedLane({
  lane,
  taskCount,
  onExpand,
}: {
  lane: SwimlaneDTO;
  taskCount: number;
  onExpand: () => void;
}) {
  const palette = lanePalette(lane);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Expand ${lane.label} lane`}
      onClick={onExpand}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand();
        }
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 14px 7px 20px',
        borderBottom: '1px solid var(--col-border)',
        borderLeft: `6px solid ${palette.accent}`,
        background: alpha(palette.color, 0.06),
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 14,
        color: palette.accent,
        position: 'sticky',
        left: 0,
      }}
    >
      <span style={{ color: 'var(--ink-faint)', fontSize: 12 }}>▸</span>
      <span>{lane.label}</span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: 'var(--ink-faint)', fontWeight: 500 }}>
        · {taskCount} task{taskCount !== 1 ? 's' : ''}
      </span>
      <span style={{ flex: 1 }} />
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: 'var(--ink-faint)' }}>
        click to expand
      </span>
    </div>
  );
}

/** The scrollable board canvas: column headers, lane rows (or flat columns), zoom. */
export function BoardGrid({ data, tweaks, view, dnd, highlight, streamOpen, onOpenTask }: BoardGridProps) {
  const { cards, cellMap, cfg, columns, emptyColumnIds, filtered, swimlanes } = data;
  // Every empty column expands back to a full drop zone for the duration of a
  // drag — a 44px rail is where cards can't be dropped, and an empty column is
  // exactly where they need to go. Expanding at drag-start reflows before the
  // user has aimed at anything, which is the cheapest moment to do it.
  const railColumns = dnd.dragging ? NO_RAILS : emptyColumnIds;
  const totalWidth = Math.max(
    400,
    LANE_LABEL_WIDTH +
      columns.reduce(
        (width, col) => width + (railColumns.has(col.id) ? COLUMN_RAIL_WIDTH : COLUMN_WIDTH),
        0,
      ),
  );

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: 'auto',
        position: 'relative',
        paddingRight: streamOpen ? 396 : 0,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          zoom: view.zoom,
          width: '100%',
          minWidth: totalWidth,
          minHeight: '100%',
        } as CSSProperties}
      >
        <BoardColumnHeaders
          data={data}
          railColumns={railColumns}
          showWipViolation={tweaks.showWipViolation}
          flashWip={dnd.flashWip}
        />

        {tweaks.showSwimlanes && swimlanes.map((lane, laneIdx) => {
          const laneCount = filtered.filter((t) => t.swimlane === lane.id).length;
          if (view.collapsed.has(lane.id)) {
            return (
              <CollapsedLane
                key={lane.id}
                lane={lane}
                taskCount={laneCount}
                onExpand={() => view.expandLane(lane.id)}
              />
            );
          }
          const palette = lanePalette(lane);
          return (
            <div
              key={lane.id}
              style={{
                display: 'flex',
                borderBottom: '1px solid var(--col-border)',
                background: alpha(palette.color, laneIdx % 2 ? 0.05 : 0.035),
                minHeight: 140,
              }}
            >
              <SwimlaneLabel
                lane={lane}
                palette={palette}
                taskCount={laneCount}
                onCollapse={() => view.collapseLane(lane.id)}
              />
              {columns.map((col) => (
                <BoardCell
                  key={col.id}
                  cards={cellMap[lane.id]?.[col.id] ?? []}
                  laneId={lane.id}
                  colId={col.id}
                  wipCap={columnWipCap(col.id, cfg?.wip_limits)}
                  rail={railColumns.has(col.id)}
                  tweaks={tweaks}
                  highlight={highlight}
                  dnd={dnd}
                  paletteFor={() => palette}
                  onOpenTask={onOpenTask}
                />
              ))}
            </div>
          );
        })}

        {!tweaks.showSwimlanes && (
          <div style={{ display: 'flex', borderBottom: '1px solid var(--col-border)', minHeight: 200 }}>
            <div
              style={{
                width: LANE_LABEL_WIDTH,
                minWidth: LANE_LABEL_WIDTH,
                flexShrink: 0,
                borderRight: '2px solid var(--line)',
                position: 'sticky',
                left: 0,
                zIndex: 1,
                background: 'var(--board)',
              }}
            />
            {columns.map((col) => (
              <BoardCell
                key={col.id}
                cards={filtered.filter((t) => t.status === col.id)}
                laneId={dnd.dragging?.swimlane ?? '__flat__'}
                colId={col.id}
                wipCap={columnWipCap(col.id, cfg?.wip_limits)}
                rail={railColumns.has(col.id)}
                tweaks={tweaks}
                highlight={highlight}
                dnd={dnd}
                paletteFor={(task) => {
                  const lane = swimlanes.find((s) => s.id === task.swimlane);
                  return lane ? lanePalette(lane) : NEUTRAL_PALETTE;
                }}
                onOpenTask={onOpenTask}
              />
            ))}
          </div>
        )}

        <div
          style={{
            padding: '14px 18px 28px',
            fontFamily: 'inherit',
            fontSize: 14,
            color: 'var(--ink-faint)',
            textAlign: 'center',
          }}
        >
          drag cards between columns · WIP caps enforced by workflow.transition() · SSoT is the Markdown frontmatter
        </div>
        <div
          aria-hidden
          style={{
            minHeight: '40vh',
            borderTop: '1px dashed var(--col-border)',
            background:
              'repeating-linear-gradient(0deg, transparent 0 39px, rgba(0,0,0,.04) 39px 40px)',
            opacity: 0.6,
          }}
        />
      </div>

      <ZoomControls
        zoom={view.zoom}
        setZoom={view.setZoom}
        collapsedCount={view.collapsed.size}
        onExpandAll={() => view.setCollapsed(new Set())}
        onCollapseEmpty={() => {
          const empty = new Set<string>();
          for (const l of swimlanes) {
            if (!cards.some((t) => t.swimlane === l.id)) empty.add(l.id);
          }
          view.setCollapsed(empty);
        }}
      />
    </div>
  );
}
