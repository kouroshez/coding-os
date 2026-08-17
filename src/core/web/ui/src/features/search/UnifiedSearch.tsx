import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Brain, FileText, KanbanSquare, Network, Search as SearchIcon } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';
import { useGraphStore } from '@/store/graph-store';

import type {
  DocsPayload,
  GraphQueryPayload,
  MemoryPayload,
  TasksPayload,
} from './search-types';
import { loadRecent, pushRecent } from './search-recent';
import { Empty, RowButton, Section, StatusTag, Tag } from './SearchPrimitives';

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
  // A layer that has not answered yet has an UNKNOWN count, not a zero one.
  // `data` is undefined while a query is in flight, so every `?? 0` above reads
  // as "searched, found nothing" — which is how the summary came to print
  // "16 results · Memory 0 · Docs 0" above three sections still saying loading….
  const pending: Record<string, boolean> = {
    Memory: memory.isLoading,
    Docs: docs.isLoading,
    Tasks: tasks.isLoading,
    Graph: graph.isLoading,
  };
  const stillCounting = Object.values(pending).some(Boolean);

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

  const layerCards = [
    { Icon: Brain, name: 'Memory', desc: 'past observations + learned patterns' },
    { Icon: FileText, name: 'Docs', desc: 'project markdown, specs, ADRs' },
    { Icon: KanbanSquare, name: 'Tasks', desc: 'the Scrumban board store' },
    { Icon: Network, name: 'Graph', desc: 'code + doc knowledge-graph nodes' },
  ];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)]/60 px-4 py-4 backdrop-blur-sm">
        <form onSubmit={onSubmit} className="mx-auto flex w-full max-w-3xl gap-2">
          <div className="relative flex-1">
            <SearchIcon
              size={15}
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--cos-muted)]"
            />
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
              placeholder="Search memory, docs, tasks, and the graph…"
              aria-label="Unified search input"
              className="w-full rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)] py-2.5 pl-9 pr-3 text-sm text-[var(--cos-text)] shadow-sm transition-colors placeholder:text-[var(--cos-faint)] focus:border-[var(--cos-accent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]/40"
            />
            {recentOpenNow && (
              <ul
                id={recentListId}
                role="listbox"
                aria-label="Recent queries"
                className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 overflow-hidden rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-lg"
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
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--cos-muted)]">
            Limit
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-2 text-xs text-[var(--cos-text)] focus:border-[var(--cos-accent)] focus:outline-none"
            >
              {[5, 8, 15, 25, 50].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="rounded-lg bg-[var(--cos-accent-solid)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            Search
          </button>
        </form>
        {submitted && (
          <div className="mx-auto mt-3 flex w-full max-w-3xl flex-wrap items-center gap-2 text-xs text-[var(--cos-muted)]">
            <span title={stillCounting ? 'one or more layers are still answering' : undefined}>
              <span className="font-semibold text-[var(--cos-text)]">{totalCount}</span>
              {stillCounting ? '+ so far' : ''} results for{' '}
              <span className="font-medium text-[var(--cos-text)]">“{submitted}”</span>
            </span>
            <span aria-hidden>·</span>
            {(
              [
                ['Memory', totals.memory],
                ['Docs', totals.docs],
                ['Tasks', totals.tasks],
                ['Graph', totals.graph],
              ] as const
            ).map(([name, n]) => (
              <span
                key={name}
                className={[
                  'rounded-full border px-2 py-0.5 text-[10px]',
                  n > 0
                    ? 'border-[var(--cos-accent)]/40 bg-[var(--cos-accent)]/10 text-[var(--cos-accent)]'
                    : 'border-[var(--cos-border)] text-[var(--cos-faint)]',
                ].join(' ')}
              >
                {name} {pending[name] ? '…' : n}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto cos-scroll p-4">
        {!submitted && (
          <div className="mx-auto max-w-2xl py-14 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-sm">
              <SearchIcon size={20} className="text-[var(--cos-accent)]" aria-hidden />
            </div>
            <h1 className="text-base font-semibold text-[var(--cos-text)]">
              Search everything this project knows
            </h1>
            <p className="mt-1 text-xs text-[var(--cos-muted)]">
              One query fans out across all four retrieval layers in parallel.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3 text-left sm:grid-cols-4">
              {layerCards.map(({ Icon, name, desc }) => (
                <div
                  key={name}
                  className="rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 p-3"
                >
                  <Icon size={16} className="mb-2 text-[var(--cos-accent)]" aria-hidden />
                  <p className="text-xs font-semibold text-[var(--cos-text)]">{name}</p>
                  <p className="mt-0.5 text-[10px] leading-snug text-[var(--cos-muted)]">{desc}</p>
                </div>
              ))}
            </div>
            {recent.length > 0 && (
              <div className="mt-6">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-[var(--cos-faint)]">
                  Recent
                </p>
                <div className="flex flex-wrap justify-center gap-1.5">
                  {recent.map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => {
                        setQ(r);
                        setSubmitted(r);
                      }}
                      className="rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2.5 py-1 text-[11px] text-[var(--cos-text)] transition-colors hover:border-[var(--cos-accent)]/60 hover:text-[var(--cos-accent)]"
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <p className="mt-6 text-[10px] text-[var(--cos-faint)]">
              Tip: press{' '}
              <kbd className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] px-1.5 py-0.5 font-mono">
                /
              </kbd>{' '}
              anywhere to jump back here
            </p>
          </div>
        )}

        {submitted && (
          <div className="mx-auto grid w-full max-w-3xl gap-6">
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

