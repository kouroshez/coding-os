import { COLUMN_META, COLUMN_RAIL_WIDTH, columnWipCap } from './board-shared';
import type { BoardData } from './useBoardData';

interface BoardColumnHeadersProps {
  data: BoardData;
  railColumns: ReadonlySet<string>;
  showWipViolation: boolean;
  flashWip: string | null;
}

/** Sticky column header row: label, WIP counter, and keyset "load more". */
export function BoardColumnHeaders({
  data,
  railColumns,
  showWipViolation,
  flashWip,
}: BoardColumnHeadersProps) {
  const { columns, columnCounts, cfg, list, extra, loadingMore, loadMore } = data;
  return (
    <div
      style={{
        display: 'flex',
        position: 'sticky',
        top: 0,
        zIndex: 5,
        background: 'var(--board)',
        borderBottom: '2px solid var(--line)',
      }}
    >
      <div
        style={{
          width: 130,
          minWidth: 130,
          flexShrink: 0,
          borderRight: '2px solid var(--line)',
          position: 'sticky',
          left: 0,
          zIndex: 2,
          background: 'var(--board)',
        }}
      />
      {columns.map((col) => {
        const count = columnCounts[col.id] ?? 0;
        const meta = COLUMN_META[col.id] ?? { label: col.label, sub: '', wip: null, tint: 'var(--ink-faint)' };
        if (railColumns.has(col.id)) {
          return (
            <div
              key={col.id}
              title={`${meta.label} — no tasks (${meta.sub})`}
              style={{
                width: COLUMN_RAIL_WIDTH,
                minWidth: COLUMN_RAIL_WIDTH,
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '10px 0 8px',
                borderTop: `3px solid ${meta.tint}`,
                borderRight: '1px dashed var(--col-border)',
              }}
            >
              <span
                style={{
                  writingMode: 'vertical-rl',
                  transform: 'rotate(180deg)',
                  fontFamily: 'inherit',
                  fontSize: 13,
                  letterSpacing: '.08em',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                  color: 'var(--ink-faint)',
                }}
              >
                {meta.label}
              </span>
            </div>
          );
        }
        const cap = columnWipCap(col.id, cfg?.wip_limits);
        const violated = showWipViolation && cap != null && count > cap;
        const colMeta = list?.columns?.[col.id];
        const paged = colMeta && colMeta.total_count != null;
        // A loaded column owns its cursor even when it is null (exhausted); only
        // an untouched column falls back to the first page's cursor.
        const more = col.id in extra ? extra[col.id].cursor : colMeta?.next_cursor;
        return (
          <div
            key={col.id}
            style={{ flex: '1 1 0', minWidth: 190, borderRight: '1px dashed var(--col-border)' }}
          >
            <div
              style={{
                position: 'sticky',
                top: 0,
                padding: '10px 12px 8px',
                borderTop: `3px solid ${meta.tint}`,
                background: violated ? 'rgba(192,57,43,.12)' : 'transparent',
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  fontFamily: 'inherit',
                  fontSize: 17,
                  letterSpacing: '.08em',
                  color: violated ? 'var(--red-ink)' : 'var(--line)',
                  textTransform: 'uppercase',
                  animation: violated ? 'shake 0.6s infinite' : 'none',
                }}
              >
                {meta.label}
              </div>
              <div style={{ fontFamily: 'inherit', fontSize: 13, color: 'var(--ink-soft)', marginTop: -2 }}>
                {meta.sub}
              </div>
              <div
                title={
                  cap != null
                    ? `WIP = work-in-progress limit: at most ${cap} task${cap !== 1 ? 's' : ''} may sit in “${meta.label}” at once`
                    : undefined
                }
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  color: violated ? 'var(--red-ink)' : 'var(--ink-faint)',
                  marginTop: 2,
                  fontWeight: violated ? 700 : 500,
                  cursor: cap != null ? 'help' : 'default',
                }}
              >
                {count}
                {cap != null ? ` / ${cap} WIP` : ' tasks'}
                {violated && ' ⚠'}
                {flashWip === col.id && <span style={{ marginLeft: 6 }}>WIP!</span>}
              </div>
              {/* Keyset-paged columns (complete/archive) show rendered / total
                  plus a "load more" affordance. */}
              {paged && (
                <div
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 10,
                    color: 'var(--ink-faint)',
                    marginTop: 1,
                  }}
                >
                  {count} / {colMeta?.total_count}
                  {more && (
                    <button
                      type="button"
                      onClick={() => void loadMore(col.id)}
                      disabled={loadingMore === col.id}
                      style={{
                        marginLeft: 6,
                        cursor: loadingMore === col.id ? 'wait' : 'pointer',
                        font: 'inherit',
                        border: '1px solid var(--col-border)',
                        borderRadius: 4,
                        background: 'transparent',
                        color: 'var(--ink-soft)',
                        padding: '0 5px',
                      }}
                    >
                      {loadingMore === col.id ? '…' : '+ more'}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
