import { useMemo, useRef, useState, type CSSProperties } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch, apiPost } from '@/lib/api-client';
import { useFocusTrap } from '@/lib/use-focus-trap';
import { renderTaskMarkdown, splitFrontmatter } from './renderTaskMarkdown';
import { kindStyle } from './kindColors';
import type { BoardListCard, SwimlaneDTO } from './types';

interface TaskDetailPayload {
  task_id: string;
  file_path: string;
  exists: boolean;
  content: string;
  size: number;
  mtime: number;
  truncated: boolean;
  row: {
    title: string;
    status: string;
    swimlane: string;
    kind: string;
    priority: string;
    appetite: string;
    epic: string | null;
    labels: string[];
  };
}

interface TaskEditFormState {
  title: string;
  priority: string;
  swimlane: string;
  appetite: string;
  labels: string;
  body: string;
}

// Exported for the modal-hardening a11y/z-index regression test
// (TaskDetailModal.test.tsx, TASK-260). Internal render site is unchanged.
export function TaskDetailDrawer({
  task,
  swimlanes,
  onClose,
}: {
  task: BoardListCard | null;
  swimlanes: SwimlaneDTO[];
  onClose: () => void;
}) {
  const laneColorFor = (swimId: string): string | undefined =>
    swimlanes.find((s) => s.id === swimId)?.color;
  const queryKey = useMemo(() => ['board-task', task?.id ?? ''], [task?.id]);
  const { data, isLoading, error } = useApiGet<TaskDetailPayload>(
    queryKey,
    task ? `/api/board/task/${task.id}` : '/api/board/task/__noop__',
    undefined,
    { enabled: !!task },
  );

  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [form, setForm] = useState<TaskEditFormState | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  // Esc-to-close + focus-trap + scroll-lock + focus-restore (a11y dialog contract).
  useFocusTrap(cardRef, { active: !!task, onClose });

  if (!task) return null;
  const titleId = `task-detail-title-${task.id}`;

  const meta = data?.row;
  const kindRaw = meta?.kind ?? task.kind;
  const kind = kindStyle(kindRaw);
  const status = (meta?.status ?? task.status).toUpperCase();
  const swimlane = meta?.swimlane ?? task.swimlane;
  const priority = meta?.priority ?? task.priority;
  const appetite = meta?.appetite ?? task.appetite ?? '1d';
  const epic = meta?.epic ?? task.epic ?? null;
  const labels = meta?.labels ?? task.labels ?? [];
  const title = meta?.title ?? task.title;
  const filePath = data?.file_path || `docs/tasks/${task.id}-...md`;

  // Priority colour — mirrors task_detail.jsx prototype palette.
  const priorityColor: Record<string, string> = {
    P0: '#dc2626',
    P1: '#ea580c',
    P2: '#ca8a04',
    P3: '#64748b',
  };
  const priColor = priorityColor[priority] ?? 'var(--ink)';

  // Strip YAML frontmatter + leading H1 (drawer header already shows title).
  let body = '';
  let editBody = '';
  if (data?.content) {
    const split = splitFrontmatter(data.content);
    // editBody keeps the full spec (Work Log included) so a save round-trips it
    // in place — the backend does a plain body replace, so the editor must send
    // the section back or it would be dropped.
    editBody = split.body.replace(/^\s*#\s+.+\n+/, '');
    // The read-only render strips the "## Work Log" section (it renders in the
    // History timeline below); only the editor keeps it.
    body = editBody.replace(/\n##\s+Work Log[\s\S]*?(?=\n##\s|$)/i, '\n');
  }

  const isReady = labels.includes('ready');
  const refresh = () => {
    void invalidateApiQueries(qc, '/api/board/list');
    void invalidateApiQueries(qc, `/api/board/task/${task.id}`);
    void invalidateApiQueries(qc, `/api/board/task/${task.id}/history`);
  };
  const enterEdit = () => {
    setForm({ title, priority, swimlane, appetite, labels: labels.join(', '), body: editBody });
    setSaveErr(null);
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setForm(null);
  };
  const saveEdit = async () => {
    if (!form) return;
    setSaving(true);
    setSaveErr(null);
    try {
      await apiPatch(`/api/board/task/${task.id}`, {
        title: form.title,
        priority: form.priority,
        swimlane: form.swimlane,
        appetite: form.appetite,
        labels: form.labels.split(',').map((s) => s.trim()).filter(Boolean),
        body: form.body,
      });
      refresh();
      setEditing(false);
      setForm(null);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };
  const toggleReady = async () => {
    try {
      await apiPost(`/api/board/task/${task.id}/ready`, { ready: !isReady });
      refresh();
    } catch {
      /* error surfaces on the next fetch */
    }
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(10,12,16,.55)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
          zIndex: 200,
          animation: 'td-fade-in 180ms ease',
        }}
      />
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          // rem cap (not px) so a 4K screen yields a much larger drawer and the
          // panel scales with browser zoom; keep translate centering (no scale).
          width: 'min(80rem, 94vw)',
          maxHeight: '90vh',
          background: 'var(--col-bg)',
          border: '1px solid var(--col-border)',
          borderRadius: 14,
          boxShadow: '0 30px 80px rgba(0,0,0,.45)',
          zIndex: 201,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'td-fade-in 180ms ease',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '14px 22px 14px',
            borderBottom: '1px solid var(--col-border)',
            background: 'linear-gradient(180deg, var(--col-bg) 0, var(--board-grain) 100%)',
            flex: '0 0 auto',
          }}
        >
          {/* file path + actions */}
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
              {data?.truncated && (
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

          {/* title row: TASK-ID + kind chip + title */}
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
              {title}
            </h1>
          </div>

          {/* metadata pills */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
            }}
          >
            <Pill label="status" value={status} />
            <Pill label="swimlane" value={swimlane} dot={laneColorFor(swimlane)} />
            <Pill label="kind" value={kindRaw} dot={kind.chip} />
            <Pill label="priority" value={priority} valueColor={priColor} strong />
            <Pill label="appetite" value={appetite} />
            {epic && <Pill label="epic" value={`#${epic}`} />}
            {labels.map((l) => (
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

        {/* Body */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '18px 28px 40px', background: 'var(--col-bg)' }}>
          {isLoading && (
            <div style={{ color: 'var(--ink-faint)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
              loading {task.id}.md…
            </div>
          )}
          {error && !isLoading && (
            <div
              style={{
                padding: 12,
                border: '1px dashed rgba(220,38,38,.4)',
                background: 'rgba(220,38,38,.06)',
                color: 'var(--cos-err)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                borderRadius: 4,
              }}
            >
              could not load task file — {error.message}
            </div>
          )}
          {data && !data.exists && !isLoading && !error && (
            <div
              style={{
                padding: 12,
                border: '1px dashed var(--col-border)',
                background: 'var(--board-grain)',
                color: 'var(--ink-faint)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                borderRadius: 4,
              }}
            >
              no file on disk for this task — DB row only.
            </div>
          )}
          {editing && form ? (
            <TaskEditForm
              form={form}
              setForm={setForm}
              swimlanes={swimlanes}
              saving={saving}
              error={saveErr}
            />
          ) : (
            <>
              {data && data.exists && (
                <div className="md-body">{renderTaskMarkdown(body)}</div>
              )}
              <TaskHistoryPanel taskId={task.id} />
            </>
          )}
        </div>

        {/* Footer — command hints from the prototype */}
        <div
          style={{
            flex: '0 0 auto',
            padding: '8px 16px',
            borderTop: '1px solid var(--col-border)',
            background: 'var(--board-grain)',
            display: 'flex',
            gap: 6,
            alignItems: 'center',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 10.5,
            color: 'var(--ink-faint)',
          }}
        >
          {editing ? (
            <>
              <button
                type="button"
                onClick={saveEdit}
                disabled={saving}
                style={{
                  background: 'var(--accent)',
                  border: '1px solid var(--accent)',
                  color: '#fff',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: saving ? 'default' : 'pointer',
                  opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? 'saving…' : '✓ save'}
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={saving}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--col-border)',
                  color: 'var(--ink-soft)',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                cancel
              </button>
              {saveErr && <span style={{ color: '#dc2626' }}>{saveErr}</span>}
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={enterEdit}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--col-border)',
                  color: 'var(--ink-soft)',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  padding: '3px 12px',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                ✎ edit
              </button>
              {status === 'ICEBOX' && (
                <button
                  type="button"
                  onClick={toggleReady}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--col-border)',
                    color: isReady ? 'var(--accent)' : 'var(--ink-soft)',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                    padding: '3px 12px',
                    borderRadius: 3,
                    cursor: 'pointer',
                  }}
                >
                  {isReady ? '✓ ready · unmark' : '○ mark ready'}
                </button>
              )}
            </>
          )}
          <span style={{ flex: 1 }} />
          <span style={{ opacity: 0.7 }}>esc close</span>
        </div>
      </div>
    </>
  );
}

function Pill({
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

function TaskChatLink({ taskId }: { taskId: string }) {
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

function TaskHistoryPanel({ taskId }: { taskId: string }) {
  const { data, isLoading } = useApiGet<TaskHistoryPayload>(
    ['board-task-history', taskId],
    `/api/board/task/${taskId}/history`,
    { include_commits: true },
    { enabled: !!taskId },
  );

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

  return (
    <div style={{ marginTop: 24, borderTop: '1px solid var(--col-border)', paddingTop: 14 }}>
      <div
        style={{
          fontFamily: baseFont,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '.08em',
          color: 'var(--ink-soft)',
          marginBottom: 8,
        }}
      >
        HISTORY
      </div>
      {s && (
        <div style={{ fontFamily: baseFont, fontSize: 11, color: 'var(--ink-faint)', marginBottom: 10 }}>
          created by {s.created_by ?? '—'}
          {s.last_edited_by ? ` · last edit by ${s.last_edited_by}` : ''}
          {s.contributors?.length ? ` · contributors: ${s.contributors.join(', ')}` : ''}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {events
          .slice()
          .reverse()
          .map((e, i) =>
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
                <span style={{ color: 'var(--ink)' }}>{describe(e)}</span>
              </div>
            ),
          )}
      </div>
    </div>
  );
}

// ---------- Task edit form (human-actor panel edit) ----------

function TaskEditForm({
  form,
  setForm,
  swimlanes,
  saving,
  error,
}: {
  form: TaskEditFormState;
  setForm: (value: TaskEditFormState | null) => void;
  swimlanes: SwimlaneDTO[];
  saving: boolean;
  error: string | null;
}) {
  const mono = "'JetBrains Mono', monospace";
  const set = (k: keyof TaskEditFormState, v: string) => setForm({ ...form, [k]: v });
  const inputStyle: CSSProperties = {
    width: '100%',
    background: 'var(--board-grain)',
    border: '1px solid var(--col-border)',
    color: 'var(--ink)',
    fontFamily: mono,
    fontSize: 12,
    padding: '6px 8px',
    borderRadius: 3,
  };
  const labelStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    fontFamily: mono,
    fontSize: 10.5,
    color: 'var(--ink-faint)',
    letterSpacing: '.04em',
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {error && <div style={{ color: '#dc2626', fontFamily: mono, fontSize: 12 }}>{error}</div>}
      <label style={labelStyle}>
        TITLE
        <input
          value={form.title}
          disabled={saving}
          onChange={(e) => set('title', e.target.value)}
          style={inputStyle}
        />
      </label>
      <div style={{ display: 'flex', gap: 12 }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          PRIORITY
          <select
            value={form.priority}
            disabled={saving}
            onChange={(e) => set('priority', e.target.value)}
            style={inputStyle}
          >
            {['P0', 'P1', 'P2', 'P3'].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 2 }}>
          SWIMLANE
          <select
            value={form.swimlane}
            disabled={saving}
            onChange={(e) => set('swimlane', e.target.value)}
            style={inputStyle}
          >
            {swimlanes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label ?? s.id}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: 1 }}>
          APPETITE
          <input
            value={form.appetite}
            disabled={saving}
            onChange={(e) => set('appetite', e.target.value)}
            style={inputStyle}
          />
        </label>
      </div>
      <label style={labelStyle}>
        LABELS (comma-separated)
        <input
          value={form.labels}
          disabled={saving}
          onChange={(e) => set('labels', e.target.value)}
          style={inputStyle}
        />
      </label>
      <label style={labelStyle}>
        BODY (markdown)
        <textarea
          value={form.body}
          disabled={saving}
          onChange={(e) => set('body', e.target.value)}
          rows={22}
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
        />
      </label>
    </div>
  );
}

