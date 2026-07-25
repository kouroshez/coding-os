import { useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch, apiPost } from '@/lib/api-client';
import { useFocusTrap } from '@/lib/use-focus-trap';
import { renderTaskMarkdown, splitFrontmatter } from './renderTaskMarkdown';
import type { BoardListCard, SwimlaneDTO } from './types';
import { TaskHistoryPanel } from './task-history';
import { TaskEditForm, type TaskEditFormState } from './task-edit-form';
import { TaskDetailHeader, resolveTaskMeta, type TaskDetailRow } from './task-detail-header';
import { TaskDetailFooter } from './task-detail-footer';

interface TaskDetailPayload {
  task_id: string;
  file_path: string;
  exists: boolean;
  content: string;
  size: number;
  mtime: number;
  truncated: boolean;
  row: TaskDetailRow;
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

  const meta = resolveTaskMeta(task, data?.row);
  const filePath = data?.file_path || `docs/tasks/${task.id}-...md`;

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

  const isReady = meta.labels.includes('ready');
  const refresh = () => {
    void invalidateApiQueries(qc, '/api/board/list');
    void invalidateApiQueries(qc, `/api/board/task/${task.id}`);
    void invalidateApiQueries(qc, `/api/board/task/${task.id}/history`);
  };
  const enterEdit = () => {
    setForm({
      title: meta.title,
      priority: meta.priority,
      swimlane: meta.swimlane,
      appetite: meta.appetite,
      labels: meta.labels.join(', '),
      body: editBody,
    });
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
        <TaskDetailHeader
          task={task}
          meta={meta}
          titleId={titleId}
          filePath={filePath}
          truncated={!!data?.truncated}
          laneColorFor={laneColorFor}
          onClose={onClose}
        />

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

        <TaskDetailFooter
          editing={editing}
          saving={saving}
          saveError={saveErr}
          isReady={isReady}
          canMarkReady={meta.status === 'ICEBOX'}
          onEdit={enterEdit}
          onSave={() => void saveEdit()}
          onCancel={cancelEdit}
          onToggleReady={() => void toggleReady()}
        />
      </div>
    </>
  );
}
