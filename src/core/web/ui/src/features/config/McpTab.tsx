import { useMemo, useState } from 'react';
import { Plus, Search, X } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { apiDelete, apiPost } from '@/lib/api-client';
import { Banner } from '@/layout/HubPrimitives';
import {
  CfgButton,
  ConfigRow,
  EmptyRow,
  Pill,
  ScopeSwitch,
  SectionCard,
  StateRow,
  TabIntro,
  useConfigMutation,
  type ConfigScope,
} from './shared';

interface McpRow {
  name: string;
  scope: string;
  transport?: string | null;
  command: string | null;
  args: string[];
  url?: string | null;
  managed: boolean;
  adapter: string;
}

interface McpCatalogRow {
  id: string;
  name: string;
  description: string;
  command: string;
  args: string[];
  installed: boolean;
}

interface McpServerGroup {
  name: string;
  managed: boolean;
  launch: string;
  installs: McpRow[];
}

const SEARCH_THRESHOLD = 8;

function launchLine(row: Pick<McpRow, 'command' | 'args' | 'url'>): string {
  return row.url || [row.command, ...row.args].filter(Boolean).join(' ') || '—';
}

// One server name configured for claude and for codex is one server the
// operator thinks about; the payload carries one row per adapter.
function groupServers(rows: McpRow[]): McpServerGroup[] {
  const groups = new Map<string, McpServerGroup>();
  for (const row of rows) {
    const group = groups.get(row.name);
    if (group) {
      group.installs.push(row);
      group.managed ||= row.managed;
    } else {
      groups.set(row.name, { name: row.name, managed: row.managed, launch: launchLine(row), installs: [row] });
    }
  }
  return [...groups.values()].sort(
    (a, b) => Number(b.managed) - Number(a.managed) || a.name.localeCompare(b.name),
  );
}

export function McpTab() {
  const [showAdd, setShowAdd] = useState(false);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<ConfigScope>('project');
  const { data, isLoading, error } = useApiGet<{ servers: McpRow[] }>(['config-mcp'], '/api/config/mcp');
  // Only fetch the allow-list catalog once the picker opens — its only render site.
  const catalog = useApiGet<{ servers: McpCatalogRow[] }>(
    ['config-mcp-catalog'],
    '/api/config/mcp/catalog',
    undefined,
    { enabled: showAdd },
  );
  const { busyId, error: mutError, setError, run } = useConfigMutation(['config-mcp', 'config-mcp-catalog']);
  const allRows = useMemo(() => data?.servers ?? [], [data]);
  const projectGroups = useMemo(() => groupServers(allRows.filter((r) => r.scope !== 'global')), [allRows]);
  const globalGroups = useMemo(() => groupServers(allRows.filter((r) => r.scope === 'global')), [allRows]);
  const groups = scope === 'global' ? globalGroups : projectGroups;
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? groups.filter((g) => `${g.name} ${g.launch}`.toLowerCase().includes(needle))
    : groups;

  if (isLoading) return <StateRow>Loading MCP servers…</StateRow>;
  if (error) return <StateRow>Could not load MCP servers: {error.message}</StateRow>;
  const catalogRows = catalog.data?.servers ?? [];
  const add = (id: string) => run(id, () => apiPost('/api/config/mcp', { id }));
  const remove = (row: McpRow) => {
    if (
      row.scope === 'global' &&
      !window.confirm(`Remove ${row.name} from ${row.adapter}'s global config? Every project on this machine loses it.`)
    ) {
      return;
    }
    const busyKey = `${row.adapter}:${row.name}`;
    run(busyKey, () =>
      apiDelete(`/api/config/mcp/${encodeURIComponent(row.name)}`, undefined, {
        adapter: row.adapter,
        scope: row.scope,
      }),
    );
  };

  return (
    <>
      <TabIntro>
        Model Context Protocol servers this project’s agents load, read from each adapter’s config.
        A server configured for several adapters is listed once. Add a vetted first-party server
        below.
      </TabIntro>
      <ScopeSwitch
        value={scope}
        onChange={setScope}
        counts={{ project: projectGroups.length, global: globalGroups.length }}
      />
      {mutError && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {mutError}
        </Banner>
      )}
      <SectionCard
        title={scope === 'global' ? 'Global servers' : 'Project servers'}
        count={groups.length}
        action={
          <CfgButton
            tone="primary"
            icon={<Plus size={13} aria-hidden />}
            onClick={() => setShowAdd((v) => !v)}
          >
            Add server
          </CfgButton>
        }
      >
        {groups.length > SEARCH_THRESHOLD && (
          <label className="relative block px-4 py-2.5">
            <span className="sr-only">Filter MCP servers</span>
            <Search
              size={13}
              aria-hidden
              className="pointer-events-none absolute start-7 top-1/2 -translate-y-1/2 text-[var(--cos-muted)]"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by name or command…"
              className="w-full rounded-lg border border-[var(--cos-border)] bg-transparent py-1.5 pe-3 ps-8 text-xs text-[var(--cos-text)] placeholder:text-[var(--cos-muted)] focus:border-[var(--accent)] focus:outline-none"
            />
          </label>
        )}
        {groups.length === 0 ? (
          <EmptyRow>
            {scope === 'global' ? 'No machine-wide MCP servers.' : 'No MCP server is configured by this project.'}
          </EmptyRow>
        ) : shown.length === 0 ? (
          <EmptyRow>No server matches “{query}”.</EmptyRow>
        ) : (
          shown.map((group) => (
            <ConfigRow
              key={group.name}
              title={group.name}
              badges={
                <>
                  {group.managed ? <Pill tone="ok">managed by cos</Pill> : <Pill tone="muted">external</Pill>}
                  {group.installs.map((row) => (
                    <span
                      key={`${row.adapter}:${row.scope}`}
                      className="inline-flex items-center gap-1 rounded-full border border-[var(--cos-border)] py-0.5 pe-1 ps-2 font-mono text-[10px] text-[var(--cos-muted)]"
                    >
                      {row.adapter}
                      <span className="text-[var(--cos-faint)]">· {row.scope}</span>
                      {!row.managed && (
                        <button
                          type="button"
                          aria-label={`Remove ${row.name} from ${row.adapter}`}
                          title={`Remove from ${row.adapter}`}
                          disabled={busyId !== null}
                          onClick={() => remove(row)}
                          className="rounded-full p-0.5 hover:bg-[var(--cos-err-tint)] hover:text-[var(--cos-err)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-40"
                        >
                          <X size={10} aria-hidden />
                        </button>
                      )}
                    </span>
                  ))}
                </>
              }
              meta={
                <span className="block max-w-[64ch] truncate font-mono text-[10px]" title={group.launch}>
                  {group.launch}
                </span>
              }
            />
          ))
        )}
      </SectionCard>
      {showAdd && (
        <SectionCard
          title="First-party servers"
          count={catalogRows.length}
          subtitle="Vetted stdio servers that need no secret."
        >
          {catalog.isLoading ? (
            <EmptyRow>Loading catalog…</EmptyRow>
          ) : (
            catalogRows.map((c) => (
              <ConfigRow
                key={c.id}
                title={c.name}
                badges={c.installed ? <Pill tone="ok">installed</Pill> : undefined}
                meta={
                  <>
                    {c.description}
                    <div className="mt-0.5 font-mono text-[10px]">{launchLine(c)}</div>
                  </>
                }
                action={
                  <CfgButton
                    tone="primary"
                    busy={busyId === c.id}
                    disabled={c.installed || (busyId !== null && busyId !== c.id)}
                    onClick={() => add(c.id)}
                    icon={<Plus size={13} aria-hidden />}
                  >
                    {c.installed ? 'Added' : 'Add'}
                  </CfgButton>
                }
              />
            ))
          )}
        </SectionCard>
      )}
    </>
  );
}
