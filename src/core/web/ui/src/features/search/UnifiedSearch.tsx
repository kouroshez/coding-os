import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';
import { useGraphStore } from '@/store/graph-store';

interface MemoryHit {
  id?: string | number | null;
  title?: string;
  summary?: string;
  content?: string;
  memory_type?: string;
  source_table?: string;
  confidence?: number;
  impact_score?: number;
  semantic_score?: number;
}

interface MemoryPayload {
  results?: MemoryHit[];
  count?: number;
}

interface DocHit {
  id?: number;
  title?: string;
  heading_path?: string;
  path?: string;
  source_path?: string;
  source_type?: string;
  snippet?: string;
  content?: string;
  score?: number;
  cosine?: number;
}

interface DocsPayload {
  results?: DocHit[];
  count?: number;
}

interface TaskHit {
  task_id?: string;
  title?: string;
  goal_text?: string;
  status?: string;
  domain?: string;
  file_path?: string;
  score?: number;
}

interface TasksPayload {
  results?: TaskHit[];
  count?: number;
}

interface GraphHit {
  uid: string;
  kind?: string;
  label?: string;
  file_path?: string;
  confidence?: number;
}

interface GraphQueryPayload {
  results?: GraphHit[];
}

const RECENT_KEY = 'cos.search.recent';
const RECENT_LIMIT = 8;

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, RECENT_LIMIT) : [];
  } catch {
    return [];
  }
}
function pushRecent(q: string): string[] {
  const next = [q, ...loadRecent().filter((r) => r !== q)].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // localStorage quota / disabled — non-fatal
  }
  return next;
}

export default function UnifiedSearch() {
  const initialQ = new URLSearchParams(window.location.search).get('q') ?? '';
  const [q, setQ] = useState(initialQ);
  const [submitted, setSubmitted] = useState(initialQ);
  const [limit, setLimit] = useState(8);
  const [recent, setRecent] = useState<string[]>(loadRecent());
  const [recentOpen, setRecentOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const setSelectedNode = useGraphStore((s) => s.setSelectedNode);
  const setRoot = useGraphStore((s) => s.setRoot);
  // Feature panels live under /p/<slug>/<feature>. Honour the current
  // slug when navigating from search results so we never bounce back to
  // the Hub project picker.
  const slugMatch = /^\/p\/([^/]+)/.exec(location.pathname);
  const slugPrefix = slugMatch ? `/p/${slugMatch[1]}` : '';

  // Global "/" shortcut to focus the input. Skip when the user is
  // typing in another field so the slash key still works in inputs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return;
      if (e.key === '/') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = q.trim();
    setSubmitted(trimmed);
    if (trimmed) setRecent(pushRecent(trimmed));
    setRecentOpen(false);
    setExpanded(null);
  };

  const memory = useApiGet<MemoryPayload>(
    ['search-memory', submitted, limit],
    '/api/search/memory',
    { query: submitted, limit },
    { enabled: submitted.length > 0 },
  );
  const docs = useApiGet<DocsPayload>(
    ['search-docs', submitted, limit],
    '/api/search/docs',
    { query: submitted, limit },
    { enabled: submitted.length > 0 },
  );
  const tasks = useApiGet<TasksPayload>(
    ['search-tasks', submitted, limit],
    '/api/search/tasks',
    { query: submitted, limit },
    { enabled: submitted.length > 0 },
  );
  const graph = useApiGet<GraphQueryPayload>(
    ['search-graph', submitted, limit * 2],
    '/api/graph/query',
    { q: submitted, limit: limit * 2 },
    { enabled: submitted.length > 0 },
  );

  const totals = {
    memory: memory.data?.results?.length ?? 0,
    docs: docs.data?.results?.length ?? 0,
    tasks: tasks.data?.results?.length ?? 0,
    graph: graph.data?.results?.length ?? 0,
  };
  const totalCount = totals.memory + totals.docs + totals.tasks + totals.graph;

  const toggle = (key: string) => setExpanded((cur) => (cur === key ? null : key));

  const openGraph = (uid: string) => {
    setRoot(uid);
    setSelectedNode(uid);
    navigate(`${slugPrefix}/graph/${encodeURIComponent(uid)}`);
  };
  const openTask = (taskId: string) => {
    navigate(`${slugPrefix}/workspace/board?task=${encodeURIComponent(taskId)}`);
  };

  const recentOpenNow = recentOpen && recent.length > 0;
  const recentListId = useId();

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)] p-4">
        <form onSubmit={onSubmit} className="relative flex gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="search"
              role="combobox"
              aria-expanded={recentOpenNow}
              aria-controls={recentListId}
              aria-autocomplete="list"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onFocus={() => setRecentOpen(recent.length > 0)}
              onBlur={() => setTimeout(() => setRecentOpen(false), 150)}
              placeholder='search memory · docs · tasks · graph        ( / to focus )'
              aria-label="Unified search input"
              className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-3 py-2 text-sm text-[var(--cos-text)] focus:border-[var(--cos-accent)] focus:outline-none"
            />
            {recentOpenNow && (
              <ul
                id={recentListId}
                role="listbox"
                aria-label="Recent queries"
                className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 overflow-hidden rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-lg"
              >
                {recent.map((r) => (
                  <li key={r} role="presentation">
                    <button
                      type="button"
                      role="option"
                      aria-selected={false}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        setQ(r);
                        setSubmitted(r);
                        setRecentOpen(false);
                      }}
                      className="block w-full px-3 py-1.5 text-left text-xs text-[var(--cos-text)] hover:bg-[var(--cos-accent)]/10"
                    >
                      {r}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <label className="flex items-center gap-1 text-[10px] text-[var(--cos-muted)]">
            limit
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-1 py-1 text-xs text-[var(--cos-text)]"
            >
              {[5, 8, 15, 25, 50].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="rounded border border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 px-3 py-2 text-sm font-semibold text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/20"
          >
            search
          </button>
        </form>
        {submitted && (
          <div className="mt-2 flex items-center gap-3 text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">
            <span>q: {submitted}</span>
            <span>·</span>
            <span>{totalCount} hits</span>
            <span>· memory {totals.memory}</span>
            <span>· docs {totals.docs}</span>
            <span>· tasks {totals.tasks}</span>
            <span>· graph {totals.graph}</span>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto cos-scroll p-4">
        {!submitted && (
          <div className="mx-auto max-w-md py-12 text-center text-sm text-[var(--cos-muted)]">
            <p className="mb-2">submit a query to search across all four retrieval layers in parallel.</p>
            <p className="text-xs">
              memory (past observations + learned patterns) · docs (project markdown) ·
              tasks (Scrumban store) · graph (knowledge graph nodes)
            </p>
            <p className="mt-4 text-[10px]">tip: press <kbd className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-1.5 py-0.5 font-mono">/</kbd> anywhere to jump back here</p>
          </div>
        )}

        {submitted && (
          <div className="grid gap-6">
            <Section title="Memory" count={totals.memory} isLoading={memory.isLoading} error={memory.error}>
              {(memory.data?.results ?? []).map((r, i) => {
                const key = `m-${r.id ?? i}`;
                const head = r.title ?? r.summary ?? '(untitled observation)';
                const body = r.content ?? r.summary;
                const open = expanded === key;
                return (
                  <RowButton key={key} active={open} onClick={() => toggle(key)}>
                    <div className="flex items-center gap-2">
                      {r.memory_type && <Tag>{r.memory_type}</Tag>}
                      {r.source_table && <Tag muted>{r.source_table}</Tag>}
                      <span className="ml-auto flex items-center gap-2 text-[10px] text-[var(--cos-muted)]">
                        {r.confidence != null && <span>conf {r.confidence.toFixed(2)}</span>}
                        {r.semantic_score != null && <span>sim {r.semantic_score.toFixed(2)}</span>}
                      </span>
                    </div>
                    <p className="mt-1 leading-snug">{head}</p>
                    {open && body && body !== head && (
                      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll">
                        {body}
                      </pre>
                    )}
                  </RowButton>
                );
              })}
              {totals.memory === 0 && !memory.isLoading && <Empty>no memory matches</Empty>}
            </Section>

            <Section title="Docs" count={totals.docs} isLoading={docs.isLoading} error={docs.error}>
              {(docs.data?.results ?? []).map((r, i) => {
                const key = `d-${r.id ?? i}`;
                const title = r.title ?? r.heading_path ?? r.source_path ?? r.path ?? '(untitled)';
                const path = r.source_path ?? r.path;
                const body = r.snippet ?? r.content;
                const score = r.score ?? r.cosine;
                const open = expanded === key;
                return (
                  <RowButton key={key} active={open} onClick={() => toggle(key)}>
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold">{title}</span>
                      {score != null && <span className="shrink-0 text-[10px] text-[var(--cos-muted)]">{score.toFixed(2)}</span>}
                    </div>
                    {path && <p className="font-mono text-[10px] text-[var(--cos-muted)]">{path}</p>}
                    {body && (
                      <p className={['mt-1 leading-snug', open ? '' : 'line-clamp-3'].join(' ')}>
                        {body}
                      </p>
                    )}
                  </RowButton>
                );
              })}
              {totals.docs === 0 && !docs.isLoading && <Empty>no doc matches</Empty>}
            </Section>

            <Section title="Tasks" count={totals.tasks} isLoading={tasks.isLoading} error={tasks.error}>
              {(tasks.data?.results ?? []).map((r, i) => {
                const key = `t-${r.task_id ?? i}`;
                const open = expanded === key;
                return (
                  <RowButton key={key} active={open} onClick={() => toggle(key)}>
                    <div className="flex items-center gap-2">
                      {r.task_id && <Tag>{r.task_id}</Tag>}
                      {r.status && <StatusTag status={r.status} />}
                      {r.domain && <Tag muted>{r.domain}</Tag>}
                      {r.score != null && <span className="ml-auto text-[10px] text-[var(--cos-muted)]">{r.score.toFixed(2)}</span>}
                    </div>
                    <p className="mt-1 font-semibold leading-snug">{r.title ?? r.task_id ?? '(untitled task)'}</p>
                    {r.file_path && <p className="font-mono text-[10px] text-[var(--cos-muted)]">{r.file_path}</p>}
                    {open && r.goal_text && (
                      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] p-2 font-mono text-[10px] text-[var(--cos-text)] cos-scroll">
                        {r.goal_text}
                      </pre>
                    )}
                    {open && r.task_id && (
                      <div className="mt-2 flex justify-end">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); openTask(r.task_id!); }}
                          className="rounded border border-[var(--cos-accent)] px-2 py-0.5 text-[10px] text-[var(--cos-accent)] hover:bg-[var(--cos-accent)]/10"
                        >
                          open in board →
                        </button>
                      </div>
                    )}
                  </RowButton>
                );
              })}
              {totals.tasks === 0 && !tasks.isLoading && <Empty>no task matches</Empty>}
            </Section>

            <Section title="Graph" count={totals.graph} isLoading={graph.isLoading} error={graph.error}>
              {(graph.data?.results ?? []).map((r) => (
                <RowButton key={r.uid} active={false} onClick={() => openGraph(r.uid)}>
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-2 rounded-sm"
                      style={{ background: kindColor(r.kind) }}
                      aria-hidden
                    />
                    <span className="font-semibold">{r.label ?? r.uid}</span>
                    <span className="ml-auto font-mono text-[10px] text-[var(--cos-muted)]">{r.kind}</span>
                  </div>
                  <p className="font-mono text-[10px] text-[var(--cos-muted)]">{r.uid}</p>
                  {r.file_path && <p className="font-mono text-[10px] text-[var(--cos-muted)]">{r.file_path}</p>}
                </RowButton>
              ))}
              {totals.graph === 0 && !graph.isLoading && <Empty>no graph matches</Empty>}
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  count,
  isLoading,
  error,
  children,
}: {
  title: string;
  count: number;
  isLoading: boolean;
  error: Error | null;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">
        <span>{title}</span>
        <span className="rounded bg-[var(--cos-border)]/40 px-1.5 py-0.5 font-mono text-[10px] text-[var(--cos-text)]">{count}</span>
        {isLoading && <span className="text-[10px] normal-case text-[var(--cos-muted)]">loading…</span>}
      </h2>
      {error && (
        <p role="alert" className="mb-2 text-xs text-[var(--cos-err)]">
          {error.message}
        </p>
      )}
      <ul className="space-y-2">{children}</ul>
    </section>
  );
}

function RowButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={[
          'block w-full rounded border bg-[var(--cos-panel)] p-2 text-left text-xs text-[var(--cos-text)] transition-colors',
          active
            ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/5'
            : 'border-[var(--cos-border)] hover:border-[var(--cos-accent)]/60',
        ].join(' ')}
      >
        {children}
      </button>
    </li>
  );
}

function Tag({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <span
      className={[
        'rounded px-1 py-0.5 text-[10px] uppercase tracking-wide',
        muted
          ? 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]'
          : 'bg-[var(--cos-accent)]/15 text-[var(--cos-accent)]',
      ].join(' ')}
    >
      {children}
    </span>
  );
}

function StatusTag({ status }: { status: string }) {
  const palette: Record<string, string> = {
    open: 'bg-[var(--cos-info-tint)] text-[var(--cos-info)]',
    wip: 'bg-[var(--cos-warn-tint)] text-[var(--cos-warn)]',
    in_progress: 'bg-[var(--cos-warn-tint)] text-[var(--cos-warn)]',
    testing: 'bg-[var(--cos-brand-tint)] text-[var(--cos-brand-text)]',
    blocked: 'bg-[var(--cos-err-tint)] text-[var(--cos-err)]',
    done: 'bg-[var(--cos-ok-tint)] text-[var(--cos-ok)]',
  };
  const cls = palette[status] ?? 'bg-[var(--cos-border)]/30 text-[var(--cos-muted)]';
  return <span className={['rounded px-1 py-0.5 text-[10px] uppercase tracking-wide', cls].join(' ')}>{status}</span>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-2 py-3 text-xs text-[var(--cos-muted)]">{children}.</p>;
}
