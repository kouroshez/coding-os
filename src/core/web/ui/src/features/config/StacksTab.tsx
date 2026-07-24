import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { apiDelete, apiPost } from '@/lib/api-client';
import { Banner } from '@/layout/HubPrimitives';
import { CfgButton, ConfigRow, EmptyRow, Pill, SectionCard, StateRow, TabIntro, useConfigMutation } from './shared';

interface StackRow {
  id: string;
  label: string;
  category: string;
  primary_skill: string | null;
  installed: boolean;
}

export function StacksTab() {
  const { data, isLoading, error } = useApiGet<{ available: StackRow[]; installed: string[] }>(
    ['config-stacks'],
    '/api/config/stacks',
  );
  const { busyId, error: mutError, setError, run } = useConfigMutation(['config-stacks', 'config-skills']);
  const [showAdd, setShowAdd] = useState(false);
  if (isLoading) return <StateRow>Loading stacks…</StateRow>;
  if (error) return <StateRow>Could not load stacks: {error.message}</StateRow>;
  const all = data?.available ?? [];
  const installed = all.filter((s) => s.installed);
  const available = all.filter((s) => !s.installed);
  const install = (id: string) => run(id, () => apiPost(`/api/config/stacks/${id}`));
  const remove = (id: string) => run(id, () => apiDelete(`/api/config/stacks/${id}`));
  const rowMeta = (s: StackRow) => (
    <>
      <span className="capitalize">{s.category}</span>
      {s.primary_skill && (
        <>
          {' · primary skill '}
          <span className="font-mono">{s.primary_skill}</span>
        </>
      )}
    </>
  );
  return (
    <>
      <TabIntro>
        The tech stacks installed in this project — each layers its skills, scaffold, and rules onto the
        agent. Add another with <span className="font-mono">+ Add stack</span>.
      </TabIntro>
      {mutError && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {mutError}
        </Banner>
      )}
      <SectionCard
        title="Installed"
        count={installed.length}
        action={
          <CfgButton
            tone="primary"
            icon={<Plus size={13} aria-hidden />}
            onClick={() => setShowAdd((v) => !v)}
          >
            Add stack
          </CfgButton>
        }
      >
        {installed.length === 0 ? (
          <EmptyRow>No stacks installed yet.</EmptyRow>
        ) : (
          installed.map((s) => (
            <ConfigRow
              key={s.id}
              title={s.label || s.id}
              meta={rowMeta(s)}
              badges={<Pill tone="ok">installed</Pill>}
              action={
                <CfgButton
                  tone="danger"
                  busy={busyId === s.id}
                  disabled={busyId !== null && busyId !== s.id}
                  title={`Remove ${s.label || s.id}`}
                  onClick={() => remove(s.id)}
                  icon={<Trash2 size={13} aria-hidden />}
                >
                  Remove
                </CfgButton>
              }
            />
          ))
        )}
      </SectionCard>
      {showAdd && (
        <SectionCard
          title="Available to add"
          count={available.length}
          subtitle="Installing a stack copies its scaffold + skills and regenerates AGENTS.md."
        >
          {available.length === 0 ? (
            <EmptyRow>Every available stack is already installed.</EmptyRow>
          ) : (
            available.map((s) => (
              <ConfigRow
                key={s.id}
                title={s.label || s.id}
                meta={rowMeta(s)}
                action={
                  <CfgButton
                    tone="primary"
                    busy={busyId === s.id}
                    disabled={busyId !== null && busyId !== s.id}
                    onClick={() => install(s.id)}
                    icon={<Plus size={13} aria-hidden />}
                  >
                    Install
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
