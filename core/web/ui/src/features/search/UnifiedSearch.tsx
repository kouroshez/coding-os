import { useState, type FormEvent } from 'react';
import { useApiGet } from '@/lib/hooks';
import { kindColor } from '@/lib/node-colors';

interface MemoryHit {
  id?: string | number;
  summary?: string;
  content?: string;
  memory_type?: string;
}

interface MemoryPayload {
  results?: MemoryHit[];
  count?: number;
}

interface DocHit {
  title?: string;
  path?: string;
  snippet?: string;
  score?: number;
}

interface DocsPayload {
  results?: DocHit[];
  count?: number;
}

interface GraphHit {
  uid: string;
  kind?: string;
  label?: string;
  score?: number;
}

interface GraphQueryPayload {
  results?: GraphHit[];
}

// Unified search page. Submitting triggers three parallel queries
// (memory, docs, graph) and renders them in stacked result sections.
export default function UnifiedSearch() {
  const initialQ = new URLSearchParams(window.location.search).get('q') ?? '';
  const [q, setQ] = useState(initialQ);
  const [submitted, setSubmitted] = useState(initialQ);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(q.trim());
  };

  const memory = useApiGet<MemoryPayload>(
    ['search-memory', submitted],
    '/api/search/memory',
    { query: submitted, limit: 5 },
    { enabled: submitted.length > 0 },
  );
  const docs = useApiGet<DocsPayload>(
    ['search-docs', submitted],
    '/api/search/docs',
    { query: submitted, limit: 5 },
    { enabled: submitted.length > 0 },
  );
  const graph = useApiGet<GraphQueryPayload>(
    ['search-graph', submitted],
    '/api/graph/query',
    { q: submitted, limit: 10 },
    { enabled: submitted.length > 0 },
  );

  return (
    <div className="flex h-full flex-col overflow-auto p-6 cos-scroll">
      <form onSubmit={onSubmit} className="mb-6 flex gap-2">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search memory, docs, graph"
          aria-label="Unified search input"
          className="flex-1 rounded border border-[#2a2f39] bg-[#0e1116] px-3 py-2 text-sm"
        />
        <button
          type="submit"
          className="rounded border border-[#7fd4a0] px-3 py-2 text-sm text-[#7fd4a0] hover:bg-[#1b3528]"
        >
          search
        </button>
      </form>

      {!submitted && (
        <p className="text-sm text-[#9ea4ae]">
          submit a query to search memory, documentation and the knowledge graph
          in parallel.
        </p>
      )}

      {submitted && (
        <div className="grid gap-6">
          <Section title="Memory" isLoading={memory.isLoading} error={memory.error}>
            {(memory.data?.results ?? []).length === 0 ? (
              <p className="text-xs text-[#9ea4ae]">no memory matches.</p>
            ) : (
              <ul className="space-y-2">
                {(memory.data?.results ?? []).map((r, i) => (
                  <li
                    key={r.id ?? i}
                    className="rounded border border-[#2a2f39] bg-[#0e1116] p-2 text-xs"
                  >
                    {r.memory_type && (
                      <span className="mr-2 rounded bg-[#2a2f39] px-1 text-[10px] text-[#9ea4ae]">
                        {r.memory_type}
                      </span>
                    )}
                    {r.summary ?? r.content ?? '(empty)'}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Docs" isLoading={docs.isLoading} error={docs.error}>
            {(docs.data?.results ?? []).length === 0 ? (
              <p className="text-xs text-[#9ea4ae]">no doc matches.</p>
            ) : (
              <ul className="space-y-2">
                {(docs.data?.results ?? []).map((r, i) => (
                  <li
                    key={`${r.path ?? i}`}
                    className="rounded border border-[#2a2f39] bg-[#0e1116] p-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{r.title ?? r.path}</span>
                      {r.score != null && (
                        <span className="text-[10px] text-[#6c7280]">
                          {r.score.toFixed(2)}
                        </span>
                      )}
                    </div>
                    {r.path && (
                      <p className="font-mono text-[10px] text-[#6c7280]">{r.path}</p>
                    )}
                    {r.snippet && <p className="mt-1 text-[#c8ccd4]">{r.snippet}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Graph" isLoading={graph.isLoading} error={graph.error}>
            {(graph.data?.results ?? []).length === 0 ? (
              <p className="text-xs text-[#9ea4ae]">no graph matches.</p>
            ) : (
              <ul className="space-y-2">
                {(graph.data?.results ?? []).map((r) => (
                  <li
                    key={r.uid}
                    className="rounded border border-[#2a2f39] bg-[#0e1116] p-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block h-2 w-2 rounded-sm"
                        style={{ background: kindColor(r.kind) }}
                        aria-hidden
                      />
                      <span>{r.label ?? r.uid}</span>
                      <span className="ml-auto font-mono text-[10px] text-[#6c7280]">
                        {r.kind}
                      </span>
                    </div>
                    <p className="font-mono text-[10px] text-[#6c7280]">{r.uid}</p>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  isLoading,
  error,
  children,
}: {
  title: string;
  isLoading: boolean;
  error: Error | null;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ea4ae]">
        {title}
      </h2>
      {isLoading && <p className="text-xs text-[#9ea4ae]">loading…</p>}
      {error && (
        <p role="alert" className="text-xs text-rose-400">
          {error.message}
        </p>
      )}
      {!isLoading && !error && children}
    </section>
  );
}
