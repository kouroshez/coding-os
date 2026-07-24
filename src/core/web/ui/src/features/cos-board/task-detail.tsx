import { useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch, apiPost } from '@/lib/api-client';
import { useFocusTrap } from '@/lib/use-focus-trap';
import { renderTaskMarkdown, splitFrontmatter } from './renderTaskMarkdown';
import { kindStyle } from './kindColors';
import type { BoardListCard, SwimlaneDTO } from './types';
import { Pill, TaskChatLink, TaskHistoryPanel } from './task-history';
import { TaskEditForm, type TaskEditFormState } from './task-edit-form';

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
