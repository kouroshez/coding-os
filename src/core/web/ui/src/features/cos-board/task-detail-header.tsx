import { kindStyle } from './kindColors';
import { Pill, TaskChatLink } from './task-history';
import type { BoardListCard } from './types';

export interface TaskDetailRow {
  title: string;
  status: string;
  swimlane: string;
  kind: string;
  priority: string;
  appetite: string;
  epic: string | null;
  labels: string[];
}

export interface ResolvedTaskMeta {
  title: string;
  status: string;
  swimlane: string;
  kind: string;
  priority: string;
  appetite: string;
  epic: string | null;
  labels: string[];
}

// The DB row is authoritative once the detail fetch lands; until then the board
// card's own fields keep the drawer populated instead of blank.
export function resolveTaskMeta(task: BoardListCard, row: TaskDetailRow | undefined): ResolvedTaskMeta {
  return {
    title: row?.title ?? task.title,
    status: (row?.status ?? task.status).toUpperCase(),
    swimlane: row?.swimlane ?? task.swimlane,
    kind: row?.kind ?? task.kind,
    priority: row?.priority ?? task.priority,
    appetite: row?.appetite ?? task.appetite ?? '1d',
    epic: row?.epic ?? task.epic ?? null,
    labels: row?.labels ?? task.labels ?? [],
  };
}

const PRIORITY_COLOR: Record<string, string> = {
  P0: '#dc2626',
  P1: '#ea580c',
  P2: '#ca8a04',
  P3: '#64748b',
};

interface TaskDetailHeaderProps {
  task: BoardListCard;
  meta: ResolvedTaskMeta;
  titleId: string;
  filePath: string;
  truncated: boolean;
  laneColorFor: (swimId: string) => string | undefined;
  onClose: () => void;
}

/** Drawer header: file path, chat link, task id + title, metadata pills. */
export function TaskDetailHeader({
  task,
  meta,
  titleId,
  filePath,
  truncated,
  laneColorFor,
  onClose,
}: TaskDetailHeaderProps) {
  const kind = kindStyle(meta.kind);
  const priColor = PRIORITY_COLOR[meta.priority] ?? 'var(--ink)';
  return (
    <div
      style={{
        padding: '14px 22px 14px',
        borderBottom: '1px solid var(--col-border)',
        background: 'linear-gradient(180deg, var(--col-bg) 0, var(--board-grain) 100%)',
        flex: '0 0 auto',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            color: 'var(--ink-faint)',
            letterSpacing: '.04em',
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
          title={filePath}
        >
          <span style={{ color: 'var(--ink-soft)' }}>📄</span>
          {filePath}
          {truncated && (
            <span
              style={{
                padding: '1px 5px',
                fontSize: 9,
                fontWeight: 700,
                background: 'var(--cos-warn)',
                color: 'white',
                borderRadius: 2,
                letterSpacing: '.04em',
              }}
            >
              TRUNC
            </span>
          )}
        </span>
        <TaskChatLink taskId={task.id} />
        <button
          type="button"
          onClick={onClose}
          title="Close (esc)"
          aria-label="Close"
          style={{
            background: 'transparent',
            border: '1px solid var(--col-border)',
            color: 'var(--ink-soft)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            padding: '3px 10px',
            borderRadius: 3,
            cursor: 'pointer',
            letterSpacing: '.02em',
          }}
        >
          esc
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 14,
            fontWeight: 700,
            color: 'var(--accent)',
            padding: '2px 7px',
            background: 'var(--board-grain)',
            border: '1px solid var(--col-border)',
            borderRadius: 3,
          }}
        >
          {task.id}
        </span>
        <h1
          id={titleId}
          style={{
            margin: 0,
            flex: 1,
            fontFamily: "'Inter', system-ui, sans-serif",
            fontSize: 22,
            fontWeight: 600,
            lineHeight: 1.25,
            color: 'var(--ink)',
            letterSpacing: '-.01em',
          }}
        >
          {meta.title}
        </h1>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
        }}
      >
        <Pill label="status" value={meta.status} />
        <Pill label="swimlane" value={meta.swimlane} dot={laneColorFor(meta.swimlane)} />
        <Pill label="kind" value={meta.kind} dot={kind.chip} />
        <Pill label="priority" value={meta.priority} valueColor={priColor} strong />
        <Pill label="appetite" value={meta.appetite} />
        {meta.epic && <Pill label="epic" value={`#${meta.epic}`} />}
        {meta.labels.map((l) => (
          <span
            key={l}
            style={{
              fontSize: 10,
              padding: '2px 7px',
              background: 'transparent',
              color: 'var(--ink-soft)',
              border: '1px dashed var(--col-border)',
              borderRadius: 10,
            }}
          >
            #{l}
          </span>
        ))}
      </div>
    </div>
  );
}
