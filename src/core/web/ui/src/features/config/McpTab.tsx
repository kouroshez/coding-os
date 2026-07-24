import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { apiDelete, apiPost } from '@/lib/api-client';
import { Banner } from '@/layout/HubPrimitives';
import { CfgButton, ConfigRow, EmptyRow, Pill, SectionCard, StateRow, TabIntro, useConfigMutation } from './shared';

interface McpRow {
  name: string;
  command: string | null;
  args: string[];
  managed: boolean;
}

interface McpCatalogRow {
  id: string;
  name: string;
  description: string;
  command: string;
  args: string[];
  installed: boolean;
}

export function McpTab() {
  const [showAdd, setShowAdd] = useState(false);
  const { data, isLoading, error } = useApiGet<{ servers: McpRow[] }>(['config-mcp'], '/api/config/mcp');
  // Only fetch the allow-list catalog once the picker opens — its only render site.
  const catalog = useApiGet<{ servers: McpCatalogRow[] }>(
    ['config-mcp-catalog'],
    '/api/config/mcp/catalog',
    undefined,
    { enabled: showAdd },
  );
  const { busyId, error: mutError, setError, run } = useConfigMutation(['config-mcp', 'config-mcp-catalog']);
  if (isLoading) return <StateRow>Loading MCP servers…</StateRow>;
  if (error) return <StateRow>Could not load MCP servers: {error.message}</StateRow>;
  const servers = data?.servers ?? [];
  const catalogRows = catalog.data?.servers ?? [];
  const add = (id: string) => run(id, () => apiPost('/api/config/mcp', { id }));
  const remove = (name: string) => run(name, () => apiDelete(`/api/config/mcp/${name}`));
  const cmdOf = (command: string | null, args: string[]) => [command, ...args].filter(Boolean).join(' ') || '—';
  return (
    <>
      <TabIntro>
        Model Context Protocol servers this project’s agents connect to (from .mcp.json). Add a vetted
        first-party server below — custom, remote (URL), and uploaded servers are handled by the
        Marketplace (coming soon).
      </TabIntro>
      {mutError && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {mutError}
        </Banner>
      )}
      <SectionCard
        title="Configured"
        count={servers.length}
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
        {servers.length === 0 ? (
          <EmptyRow>No MCP servers configured.</EmptyRow>
        ) : (
          servers.map((s) => (
            <ConfigRow
              key={s.name}
              title={s.name}
              badges={s.managed ? <Pill tone="ok">managed by cos</Pill> : <Pill tone="muted">external</Pill>}
              meta={<span className="font-mono text-[10px]">{cmdOf(s.command, s.args)}</span>}
              action={
                s.managed ? undefined : (
                  <CfgButton
                    tone="danger"
                    busy={busyId === s.name}
                    disabled={busyId !== null && busyId !== s.name}
                    onClick={() => remove(s.name)}
                    icon={<Trash2 size={13} aria-hidden />}
                  >
                    Remove
                  </CfgButton>
                )
              }
            />
          ))
        )}
      </SectionCard>
      {showAdd && (
        <SectionCard
          title="First-party servers"
          count={catalogRows.length}
          subtitle="Vetted stdio servers that need no secret. Custom / URL / uploaded servers go through the Extension Manager (coming soon)."
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
                    <div className="mt-0.5 font-mono text-[10px]">{cmdOf(c.command, c.args)}</div>
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

