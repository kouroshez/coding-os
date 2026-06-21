import type { ReactNode } from 'react';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';

/**
 * Per-project Configuration surface. Shows what tech stacks, skills, MCP
 * servers, hooks, and modules are wired for the active project so a human can
 * SEE the setup without reading YAML/JSON. Modules and extra skills ARE
 * toggleable here (subsystems-state.json / .coding-os.yaml); stacks, MCP, and
 * hooks stay read-only — per-project enable/disable for those is a separate
 * kernel-override epic (a toggle must never edit the global registry).
 */

type Tab = 'stacks' | 'skills' | 'mcp' | 'hooks' | 'modules';
const TABS: Tab[] = ['stacks', 'skills', 'mcp', 'hooks', 'modules'];
const TAB_LABEL: Record<Tab, string> = {
  stacks: 'Stacks',
  skills: 'Skills',
  mcp: 'MCP Servers',
  hooks: 'Hooks',
  modules: 'Modules',
};

export default function ConfigPage() {
  const [search, setSearch] = useSearchParams();
  const raw = search.get('tab');
  const tab: Tab = (TABS as string[]).includes(raw ?? '') ? (raw as Tab) : 'stacks';
  const setTab = (t: Tab) => {
    const sp = new URLSearchParams(search);
    if (t === 'stacks') sp.delete('tab');
    else sp.set('tab', t);
    setSearch(sp, { replace: true });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SubNav
        tablist
        ariaLabel="Configuration sections"
        right={<span className="text-[11px] tracking-tight text-[var(--cos-faint)]">read-only</span>}
      >
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`${subNavTabClass(tab === t)} cursor-pointer`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </SubNav>
      <div className="min-h-0 flex-1 overflow-auto cos-scroll">
        <div className="mx-auto w-full max-w-5xl px-6 py-6">
          {tab === 'stacks' && <StacksTab />}
          {tab === 'skills' && <SkillsTab />}
          {tab === 'mcp' && <McpTab />}
          {tab === 'hooks' && <HooksTab />}
          {tab === 'modules' && <ModulesTab />}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Shared table chrome
// --------------------------------------------------------------------------

function TabIntro({ children }: { children: ReactNode }) {
  return <p className="mb-4 text-sm text-[var(--cos-muted)]">{children}</p>;
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--cos-border)]">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-[var(--cos-border)] bg-[var(--cos-panel)]/60">
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-semibold tracking-wide text-[var(--cos-muted)]">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Pill({ tone, children }: { tone: 'ok' | 'muted'; children: ReactNode }) {
  const cls =
    tone === 'ok'
      ? 'border-[var(--cos-ok)] bg-[var(--cos-ok-tint)] text-[var(--cos-ok)]'
      : 'border-[var(--cos-border)] text-[var(--cos-muted)]';
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>{children}</span>;
}

function StateRow({ children }: { children: ReactNode }) {
  return <p className="px-1 py-6 text-sm text-[var(--cos-muted)]">{children}</p>;
}

// --------------------------------------------------------------------------
// Tabs
// --------------------------------------------------------------------------

interface StackRow {
  id: string;
  label: string;
  category: string;
  primary_skill: string | null;
  installed: boolean;
}

function StacksTab() {
  const { data, isLoading, error } = useApiGet<{ available: StackRow[]; installed: string[] }>(
    ['config-stacks'],
    '/api/config/stacks',
  );
  if (isLoading) return <StateRow>Loading stacks…</StateRow>;
  if (error) return <StateRow>Could not load stacks: {error.message}</StateRow>;
  const rows = data?.available ?? [];
  return (
    <>
      <TabIntro>Tech stacks available to this project. Installed stacks shape the agent’s skills and scaffold.</TabIntro>
      <Table head={['Stack', 'Category', 'Primary skill', 'Status']}>
        {rows.map((s) => (
          <tr key={s.id} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
            <td className="px-3 py-2 font-medium text-[var(--cos-text)]">{s.label || s.id}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{s.category}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{s.primary_skill ?? '—'}</td>
            <td className="px-3 py-2">{s.installed ? <Pill tone="ok">Installed</Pill> : <Pill tone="muted">Available</Pill>}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}

interface SkillRow {
  name: string;
  tier: string;
  domain: string[];
  globs: string | null;
  description?: string;
  extra?: boolean;
  // Producer fields (config_skills) that let the Hub disable a core/stack skill,
  // not just add a community one (HUB-PB1 / TASK-503).
  provenance?: string;
  disabled?: boolean;
}

function SkillsTab() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ skills: SkillRow[] }>(['config-skills'], '/api/config/skills');
  const [pending, setPending] = useState<string | null>(null);
  if (isLoading) return <StateRow>Loading skills…</StateRow>;
  if (error) return <StateRow>Could not load skills: {error.message}</StateRow>;
  const rows = data?.skills ?? [];
  // Core/stack skills ship by default → Enable/Disable via disabled_skills.
  // Community skills are opt-in → add/remove via extra_skills. The PATCH route
  // (set_project_skill) already routes by provenance; the UI just sends intent.
  const isCoreStack = (s: SkillRow) => s.provenance === 'core' || s.provenance === 'stack';
  const isOn = (s: SkillRow) => (isCoreStack(s) ? !s.disabled : !!s.extra);
  const toggle = async (skill: SkillRow) => {
    setPending(skill.name);
    try {
      const nextEnabled = isCoreStack(skill) ? !!skill.disabled : !skill.extra;
      await apiPatch(`/api/config/skills/${skill.name}`, { enabled: nextEnabled });
      await invalidateApiQueries(queryClient, 'config-skills');
    } finally {
      setPending(null);
    }
  };
  const stateLabel = (s: SkillRow) => {
    if (pending === s.name) return '…';
    if (isCoreStack(s)) return s.disabled ? 'off' : 'on ✓';
    return s.extra ? 'extra ✓' : 'add';
  };
  const actionVerb = (s: SkillRow) =>
    isCoreStack(s) ? (s.disabled ? 'Enable' : 'Disable') : s.extra ? 'Remove' : 'Add';
  return (
    <>
      <TabIntro>Skills the agent can load. They are glob-gated — the agent loads one automatically before editing matching files. Core/stack skills ship by default; disable one to drop it for this project. “extra” marks community skills added beyond the stacks.</TabIntro>
      <Table head={['Skill', 'Tier', 'Domain', 'Triggers on', 'State']}>
        {rows.map((s) => (
          <tr key={s.name} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
            <td className="px-3 py-2 font-medium text-[var(--cos-text)]">{s.name}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{s.tier}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{s.domain.join(', ') || '—'}</td>
            <td className="px-3 py-2 font-mono text-[10px] text-[var(--cos-faint)]">{s.globs ?? '—'}</td>
            <td className="px-3 py-2">
              <button
                type="button"
                disabled={pending === s.name}
                onClick={() => void toggle(s)}
                aria-label={`${actionVerb(s)} ${s.name}`}
                aria-pressed={isOn(s)}
                className={`rounded px-2 py-0.5 text-[10px] focus-visible:ring-2 ${
                  isOn(s)
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : 'bg-white/5 text-[var(--cos-faint)] hover:text-[var(--cos-muted)]'
                }`}
              >
                {stateLabel(s)}
              </button>
            </td>
          </tr>
        ))}
      </Table>
    </>
  );
}

interface McpRow {
  name: string;
  command: string | null;
  args: string[];
  managed: boolean;
}

function McpTab() {
  const { data, isLoading, error } = useApiGet<{ servers: McpRow[] }>(['config-mcp'], '/api/config/mcp');
  if (isLoading) return <StateRow>Loading MCP servers…</StateRow>;
  if (error) return <StateRow>Could not load MCP servers: {error.message}</StateRow>;
  const rows = data?.servers ?? [];
  return (
    <>
      <TabIntro>Model Context Protocol servers the agent connects to in this project (from .mcp.json).</TabIntro>
      {rows.length === 0 ? (
        <StateRow>No MCP servers configured.</StateRow>
      ) : (
        <Table head={['Server', 'Command', 'Status']}>
          {rows.map((s) => (
            <tr key={s.name} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
              <td className="px-3 py-2 font-medium text-[var(--cos-text)]">{s.name}</td>
              <td className="px-3 py-2 font-mono text-[10px] text-[var(--cos-faint)]">
                {[s.command, ...s.args].filter(Boolean).join(' ') || '—'}
              </td>
              <td className="px-3 py-2">{s.managed ? <Pill tone="ok">Managed by cos</Pill> : <Pill tone="muted">External</Pill>}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}

interface HookRow {
  name: string;
  event: string;
  matcher?: string | null;
  category: string;
  phase?: string | null;
}

function HooksTab() {
  const { data, isLoading, error } = useApiGet<{ hooks: HookRow[] }>(['config-hooks'], '/api/hooks/list');
  if (isLoading) return <StateRow>Loading hooks…</StateRow>;
  if (error) return <StateRow>Could not load hooks: {error.message}</StateRow>;
  const rows = data?.hooks ?? [];
  return (
    <>
      <TabIntro>
        Hooks that steer the agent inside its guardrails. {rows.length} registered. Safety hooks cannot be disabled.
      </TabIntro>
      <Table head={['Hook', 'Event', 'Category', 'Phase']}>
        {rows.map((h) => (
          <tr key={h.name} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
            <td className="px-3 py-2 font-medium text-[var(--cos-text)]">{h.name}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{h.event}</td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">{h.category}</td>
            <td className="px-3 py-2 text-[var(--cos-faint)]">{h.phase ?? '—'}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}

interface ModuleRow {
  id: string;
  label: string;
  kernel: boolean;
  enabled: boolean;
  depends_on: string[];
  hooks: number;
  tools: number;
}

interface DriftRow {
  id: string;
  severity: string;
  message: string;
}

function ModulesTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ modules: ModuleRow[] }>(
    ['settings-modules'],
    '/api/settings/modules',
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  // A Hub toggle can strand a skill/command symlink or corrupt state; surface
  // the same `cos doctor` drift checks so the UI that caused it shows it (HUB-PB2).
  const { data: driftData } = useApiGet<{ drift: DriftRow[]; ok: boolean }>(
    ['settings-modules-drift'],
    '/api/settings/modules/drift',
  );

  if (isLoading) return <StateRow>Loading modules…</StateRow>;
  if (error) return <StateRow>Could not load modules: {error.message}</StateRow>;
  const rows = data?.modules ?? [];
  const drift = driftData?.drift ?? [];

  const toggle = async (row: ModuleRow) => {
    setBusyId(row.id);
    setToggleError(null);
    try {
      await apiPatch(`/api/settings/modules/${encodeURIComponent(row.id)}`, {
        enabled: !row.enabled,
      });
      await invalidateApiQueries(qc, '/api/settings/modules');
      await invalidateApiQueries(qc, '/api/settings/modules/drift');
    } catch (err) {
      setToggleError(err instanceof Error ? err.message : 'toggle failed');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <TabIntro>
        Subsystem modules for this project. The kernel is always on; disabling a module gates its
        MCP tools and self-skips its hooks (re-enable any time — state lives in
        .coding-os/subsystems-state.json).
      </TabIntro>
      {toggleError && (
        <p role="alert" className="mb-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-400">
          {toggleError}
        </p>
      )}
      {drift.length > 0 && (
        <div role="alert" className="mb-3 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-300">
          <div className="font-medium">⚠️ Module drift detected ({drift.length}) — a disabled module left an artifact behind</div>
          <ul className="mt-1 list-disc pl-4 text-amber-200/90">
            {drift.map((d) => (
              <li key={d.id}>
                <span className="font-mono">{d.id}</span>: {d.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Table head={['Module', 'State', 'Owns', 'Depends on', '']}>
        {rows.map((m) => (
          <tr key={m.id} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
            <td className="px-3 py-2">
              <div className="font-medium text-[var(--cos-text)]">{m.id}</div>
              <div className="text-[10px] text-[var(--cos-faint)]">{m.label}</div>
            </td>
            <td className="px-3 py-2">
              {m.kernel ? (
                <Pill tone="muted">kernel · locked</Pill>
              ) : (
                <Pill tone={m.enabled ? 'ok' : 'muted'}>{m.enabled ? 'enabled' : 'disabled'}</Pill>
              )}
            </td>
            <td className="px-3 py-2 text-[var(--cos-muted)]">
              {m.hooks} hooks · {m.tools} tools
            </td>
            <td className="px-3 py-2 text-[var(--cos-faint)]">{m.depends_on.join(', ') || '—'}</td>
            <td className="px-3 py-2 text-right">
              {!m.kernel && (
                <button
                  type="button"
                  data-testid={`module-toggle-${m.id}`}
                  onClick={() => void toggle(m)}
                  disabled={busyId !== null}
                  aria-pressed={m.enabled}
                  className="rounded border border-[var(--cos-border)] px-2.5 py-1 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
                >
                  {busyId === m.id ? '…' : m.enabled ? 'Disable' : 'Enable'}
                </button>
              )}
            </td>
          </tr>
        ))}
      </Table>
    </>
  );
}
