import { useState, type CSSProperties } from 'react';
import { useApiGet } from '@/lib/hooks';

export function Pill({
  label,
  value,
  strong,
  dot,
  valueColor,
}: {
  label: string;
  value: string;
  strong?: boolean;
  dot?: string;
  valueColor?: string;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 7px 2px 5px',
        background: 'var(--board-grain)',
        border: '1px solid var(--col-border)',
        borderRadius: 3,
      }}
    >
      {dot && <span style={{ width: 7, height: 7, borderRadius: 2, background: dot }} />}
      <span style={{ color: 'var(--ink-faint)' }}>{label}</span>
      <span style={{ color: valueColor ?? 'var(--ink)', fontWeight: strong ? 700 : 500 }}>{value}</span>
    </span>
  );
}

// ---------- Task history (create + status + edits + commits) ----------

interface TaskHistoryEvent {
  type: 'created' | 'status' | 'edit' | 'commit' | 'worklog';
  at: number;
  actor?: { type: string; id: string; label: string };
  from?: string | null;
  to?: string;
  reason?: string | null;
  override_reason?: string | null;
  field?: string;
  sha?: string;
  subject?: string;
  text?: string;
}

interface TaskHistoryPayload {
  task_id: string;
  events: TaskHistoryEvent[];
  summary: {
    created_by: string | null;
    created_at: number | null;
    last_edited_by: string | null;
    last_edited_at: number | null;
    contributors: string[];
    commit_count: number;
  };
  count: number;
}

const HISTORY_ICON: Record<TaskHistoryEvent['type'], string> = {
  created: '✦',
  status: '→',
  edit: '✎',
  commit: '⎇',
  worklog: '✐',
};

interface TimelineRow {
  event: TaskHistoryEvent;
  repeats: number;
}

const COMMIT_ECHO_PATTERN = /^commit(?:ted)?\s+([0-9a-f]{7,40})\b/i;

// A work-log bullet like "commit fe32399c57 — …" duplicates the commit row the
// panel already renders from git; sha lengths differ per source, so match on
// either prefix direction.
export function isCommitEcho(event: TaskHistoryEvent, commitShas: string[]): boolean {
  if (event.type !== 'worklog' || !event.text) return false;
  const match = COMMIT_ECHO_PATTERN.exec(event.text);
  if (!match) return false;
  const echoSha = match[1].toLowerCase();
  return commitShas.some((sha) => sha.startsWith(echoSha) || echoSha.startsWith(sha));
}

export function collapseRepeats(events: TaskHistoryEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (const event of events) {
    const previous = rows[rows.length - 1];
    const collapsible = event.type === 'worklog' || event.type === 'edit';
    if (
      previous &&
      collapsible &&
      previous.event.type === event.type &&
      previous.event.text === event.text &&
      previous.event.field === event.field &&
      previous.event.actor?.label === event.actor?.label
    ) {
      previous.repeats += 1;
      previous.event = { ...previous.event, at: event.at };
      continue;
    }
    rows.push({ event, repeats: 1 });
  }
  return rows;
}

interface CommitFileDTO {
  path: string;
  added: number | null;
  removed: number | null;
  binary: boolean;
}
interface CommitDetailDTO {
  sha: string;
  subject: string;
  author: string;
  date: string;
  files: CommitFileDTO[];
}
interface FileDiffDTO {
  sha: string;
  file: string;
  diff: string;
  added: number;
  removed: number;
  truncated: boolean;
}

const linkBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  padding: 0,
  cursor: 'pointer',
  textAlign: 'left',
  color: 'inherit',
};

function DiffView({ diff }: { diff: string }) {
  const mono = "'JetBrains Mono', monospace";
  return (
    <pre
      style={{
        margin: '6px 0 4px',
        padding: '8px 10px',
        background: 'var(--board-grain)',
        border: '1px solid var(--col-border)',
        borderRadius: 6,
        fontFamily: mono,
        fontSize: 10.5,
        lineHeight: 1.5,
        overflowX: 'auto',
        maxHeight: 320,
      }}
    >
      {diff.split('\n').map((ln, i) => {
        let color = 'var(--ink-soft)';
        if (ln.startsWith('+') && !ln.startsWith('+++')) color = 'var(--green)';
        else if (ln.startsWith('-') && !ln.startsWith('---')) color = 'var(--red)';
        else if (ln.startsWith('@@')) color = 'var(--accent)';
        return (
          <div key={i} style={{ color, whiteSpace: 'pre' }}>
            {ln || ' '}
          </div>
        );
      })}
    </pre>
  );
}

function FileDiffRow({ sha, file }: { sha: string; file: CommitFileDTO }) {
  const [open, setOpen] = useState(false);
  const mono = "'JetBrains Mono', monospace";
  const { data, isLoading } = useApiGet<FileDiffDTO>(
    ['board-diff', sha, file.path],
    '/api/board/diff',
    { sha, file: file.path },
    { enabled: open },
  );
  return (
    <div style={{ marginLeft: 18 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{ ...linkBtn, fontFamily: mono, fontSize: 10.5, color: 'var(--ink)' }}
      >
        <span style={{ color: 'var(--ink-faint)' }}>{open ? '▾' : '▸'}</span> {file.path}
        {file.added != null && <span style={{ color: 'var(--green)', marginLeft: 6 }}>+{file.added}</span>}
        {file.removed != null && <span style={{ color: 'var(--red)', marginLeft: 4 }}>−{file.removed}</span>}
      </button>
      {open &&
        (isLoading ? (
          <div style={{ marginLeft: 18, fontSize: 10.5, color: 'var(--ink-faint)' }}>loading diff…</div>
        ) : data ? (
          <DiffView diff={data.diff} />
        ) : null)}
    </div>
  );
}

function CommitRow({
  e,
  fmt,
  baseFont,
  taskId,
}: {
  e: TaskHistoryEvent;
  fmt: (at: number) => string;
  baseFont: string;
  taskId: string;
}) {
  const [open, setOpen] = useState(false);
  const sha = e.sha ?? '';
  // for_task scopes the commit's file list to THIS task — a batched commit
  // (many TASK-*.md in one) no longer leaks sibling files into this history.
  const { data, isLoading } = useApiGet<CommitDetailDTO>(
    ['board-commit', sha, taskId],
    `/api/board/commit/${sha}`,
    { for_task: taskId },
    { enabled: open && !!sha },
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', gap: 8, fontFamily: baseFont, fontSize: 11, alignItems: 'baseline' }}>
        <span style={{ color: 'var(--accent)', width: 12, flex: '0 0 auto' }}>{HISTORY_ICON.commit}</span>
        <span style={{ color: 'var(--ink-faint)', minWidth: 132, flex: '0 0 auto' }}>{fmt(e.at)}</span>
        <button
          onClick={() => setOpen((v) => !v)}
          style={{ ...linkBtn, color: 'var(--ink)', fontFamily: baseFont, fontSize: 11 }}
        >
          <span style={{ color: 'var(--ink-faint)' }}>{open ? '▾' : '▸'}</span> commit {sha.slice(0, 8)} ·{' '}
          {e.subject}
        </button>
      </div>
      {open && (
        <div style={{ marginLeft: 152, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {isLoading ? (
            <div style={{ fontFamily: baseFont, fontSize: 10.5, color: 'var(--ink-faint)' }}>loading files…</div>
          ) : (
            (data?.files ?? []).map((f) => <FileDiffRow key={f.path} sha={sha} file={f} />)
          )}
        </div>
      )}
    </div>
  );
}

interface ChatRefDTO {
  task_id: string;
  agent_session: string | null;
  sdk_uuid: string | null;
  has_snapshot: boolean;
}

export function TaskChatLink({ taskId }: { taskId: string }) {
  const { data } = useApiGet<ChatRefDTO>(
    ['board-chat-ref', taskId],
    `/api/board/task/${taskId}/chat-ref`,
    undefined,
    { enabled: !!taskId },
  );
  const sdkUuid = data?.sdk_uuid ?? null;
  // Only surface the action when there is a resolvable chat target. The old
  // "snapshot below" disabled state promised a transcript view that the API
  // no longer serves (board.py:758) — a dead promise, so we hide it instead.
  // The "start a new chat seeded with this task" fallback lands with the
  // Phase-2 chat landing.
  if (!sdkUuid) return null;
  const open = () => {
    const m = window.location.pathname.match(/^\/p\/[^/]+/);
    const prefix = m ? m[0] : '';
    // Land on the resumable chat workspace (ChatLanding → ChatView + follow-up
    // composer), NOT the read-only cognition trace viewer — the point is to
    // continue the conversation, not just read it.
    window.open(`${prefix}/workspace/chat/${encodeURIComponent(sdkUuid)}`, '_blank', 'noopener');
  };
  return (
    <button
      type="button"
      onClick={open}
      title="Open the chat session that created this task"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: 'var(--accent)',
        border: '1px solid var(--accent)',
        color: '#fff',
        fontFamily: "'Inter', system-ui, sans-serif",
        fontSize: 12,
        fontWeight: 600,
        padding: '5px 12px',
        borderRadius: 6,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      Open chat session
    </button>
  );
}

export function TaskHistoryPanel({ taskId }: { taskId: string }) {
  const { data, isLoading } = useApiGet<TaskHistoryPayload>(
    ['board-task-history', taskId],
    `/api/board/task/${taskId}/history`,
    { include_commits: true },
    { enabled: !!taskId },
  );
  const [showDetails, setShowDetails] = useState(false);

  const baseFont = "'JetBrains Mono', monospace";
  if (isLoading) {
    return (
      <div style={{ marginTop: 24, fontFamily: baseFont, fontSize: 11, color: 'var(--ink-faint)' }}>
        loading history…
      </div>
    );
  }
  const events = data?.events ?? [];
  if (!events.length) return null;
  const s = data?.summary;
  const fmt = (at: number) => (at ? new Date(at * 1000).toLocaleString() : '');

  const describe = (e: TaskHistoryEvent): string => {
    const who = e.actor?.label ?? '—';
    if (e.type === 'created') return `created by ${who}`;
    if (e.type === 'status') {
      const reason = e.override_reason || e.reason;
      return `${e.from ?? ''} → ${e.to} · ${who}${reason ? ` (${reason})` : ''}`;
    }
    if (e.type === 'edit') return `edited ${e.field} · ${who}`;
    if (e.type === 'worklog') return `${e.text ?? ''} · ${who}`;
    return `commit ${e.sha} · ${e.subject}`;
  };

  const commitShas = events
    .filter((e) => e.type === 'commit' && e.sha)
    .map((e) => (e.sha as string).toLowerCase());
  const detailRows = collapseRepeats(events.filter((e) => !isCommitEcho(e, commitShas)));
  const commitRows = detailRows.filter((row) => row.event.type === 'commit');
  const hiddenCount = detailRows.length - commitRows.length;
  // With zero commits the collapsed view would be empty — show the full stream.
  const detailsOpen = showDetails || commitRows.length === 0;
  const rows = detailsOpen ? detailRows : commitRows;

  return (
    <div style={{ marginTop: 24, borderTop: '1px solid var(--col-border)', paddingTop: 14 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div
          style={{
            fontFamily: baseFont,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '.08em',
            color: 'var(--ink-soft)',
          }}
        >
          HISTORY
        </div>
        {commitRows.length > 0 && hiddenCount > 0 && (
          <button
            onClick={() => setShowDetails((v) => !v)}
            style={{ ...linkBtn, fontFamily: baseFont, fontSize: 10.5, color: 'var(--ink-faint)' }}
          >
            {showDetails ? '▾ hide details' : `▸ show details (${hiddenCount} more)`}
          </button>
        )}
      </div>
      {s && (
        <div style={{ fontFamily: baseFont, fontSize: 11, color: 'var(--ink-faint)', marginBottom: 10 }}>
          created by {s.created_by ?? '—'}
          {s.last_edited_by ? ` · last edit by ${s.last_edited_by}` : ''}
          {s.contributors?.length ? ` · contributors: ${s.contributors.join(', ')}` : ''}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rows
          .slice()
          .reverse()
          .map(({ event: e, repeats }, i) =>
            e.type === 'commit' && e.sha ? (
              <CommitRow key={`commit-${e.sha}-${i}`} e={e} fmt={fmt} baseFont={baseFont} taskId={taskId} />
            ) : (
              <div
                key={`${e.type}-${e.at}-${i}`}
                style={{ display: 'flex', gap: 8, fontFamily: baseFont, fontSize: 11, alignItems: 'baseline' }}
              >
                <span style={{ color: 'var(--accent)', width: 12, flex: '0 0 auto' }}>
                  {HISTORY_ICON[e.type]}
                </span>
                <span style={{ color: 'var(--ink-faint)', minWidth: 132, flex: '0 0 auto' }}>{fmt(e.at)}</span>
                <span style={{ color: 'var(--ink)' }}>
                  {describe(e)}
                  {repeats > 1 && <span style={{ color: 'var(--ink-faint)' }}> ×{repeats}</span>}
                </span>
              </div>
            ),
          )}
      </div>
    </div>
  );
}

// ---------- Task edit form (human-actor panel edit) ----------
