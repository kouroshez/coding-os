import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
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

type Tab = 'stacks' | 'skills' | 'mcp' | 'hooks' | 'modules' | 'git';
const TABS: Tab[] = ['stacks', 'skills', 'mcp', 'hooks', 'modules', 'git'];
const TAB_LABEL: Record<Tab, string> = {
  stacks: 'Stacks',
  skills: 'Skills',
  mcp: 'MCP Servers',
  hooks: 'Hooks',
  modules: 'Modules',
  git: 'Git',
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
          {tab === 'git' && <GitTab />}
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

// --------------------------------------------------------------------------
// Git — pr-mode multi-agent workflow (settings-gated, default OFF). TASK-518.
// Project-scoped config (each project has its own hub-settings.json), so it
// lives in Config, not the hub-level Settings page where model_routing sits.
// --------------------------------------------------------------------------

type AutonomyLevel = 'local' | 'draft' | 'auto_merge' | 'autonomous';

interface GitSettings {
  enabled: boolean;
  integration_branch: string;
  protected_branches: string[];
  autonomy_level: AutonomyLevel;
}

// Ordered low→high trust. `needsRemote` rungs push/PR and are unavailable when
// the probe reports no remote+gh; `local` always works (TASK-540).
const AUTONOMY_OPTIONS: {
  value: AutonomyLevel;
  label: string;
  hint: string;
  needsRemote: boolean;
}[] = [
  { value: 'local', label: 'Local — never pushes', hint: 'Agent commits in the worktree but never pushes; a human reviews the branch and integrates. Works with no remote.', needsRemote: false },
  { value: 'draft', label: 'Draft — human merges', hint: 'Agent pushes + opens the PR; a human reviews and merges. Safe default.', needsRemote: true },
  { value: 'auto_merge', label: 'Auto-merge on green CI', hint: 'Arms auto-merge when a required check exists; the PR merges itself once green.', needsRemote: true },
  { value: 'autonomous', label: 'Autonomous — full lifecycle', hint: 'Auto-merge plus the driver loop cleans up the worktree after merge.', needsRemote: true },
];

interface GitState {
  remote: boolean;
  gh: boolean;
  required_check: boolean;
  pr_ok: boolean;
  missing: string[];
  // Real repo state (TASK-534) — sourced from local git, present even when gh is down.
  branches: string[];
  current_branch: string;
  remote_url: string;
}

const inputClass =
  'mt-1 w-full rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-2.5 py-1.5 text-sm text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none';

function GitTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ settings: { git_settings: GitSettings } }>(
    ['settings-git'],
    '/api/settings',
  );
  const loaded = data?.settings?.git_settings;
  const [form, setForm] = useState<GitSettings | null>(null);
  // Probe (incl. the gh-api required-check round-trip) only when pr-mode is on;
  // staleTime caches it so re-opening the tab doesn't re-round-trip (TASK-534).
  const probeEnabled = form ? form.enabled : !!loaded?.enabled;
  const {
    data: state,
    isLoading: stateLoading,
    error: stateError,
  } = useApiGet<GitState>(['settings-git-state'], '/api/settings/git-state', undefined, {
    enabled: probeEnabled,
    staleTimeMs: 60_000,
  });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Seed the form once when settings arrive; deps gate the effect so it never loops.
  useEffect(() => {
    if (loaded && form === null) setForm(loaded);
  }, [loaded, form]);

  if (isLoading) return <StateRow>Loading git settings…</StateRow>;
  if (error) return <StateRow>Could not load git settings: {error.message}</StateRow>;
  if (!form) return <StateRow>Loading…</StateRow>;

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await apiPatch('/api/settings', {
        git_settings: {
          enabled: form.enabled,
          integration_branch: form.integration_branch.trim() || 'main',
          protected_branches: form.protected_branches,
          autonomy_level: form.autonomy_level,
        },
      });
      await invalidateApiQueries(qc, 'settings-git');
      await invalidateApiQueries(qc, 'settings-git-state');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };

  const branches = state?.branches ?? [];
  const hasBranchList = branches.length > 0;
  // Warn (never block) when a configured branch doesn't exist in the repo — the
  // free-text trap that let a consumer silently set a non-existent branch.
  const unknownBranches = hasBranchList
    ? [form.integration_branch, ...form.protected_branches]
        .map((b) => b.trim())
        .filter((b) => b && !branches.includes(b))
    : [];
  const toggleProtected = (branch: string, on: boolean) =>
    setForm({
      ...form,
      protected_branches: on
        ? [...form.protected_branches, branch]
        : form.protected_branches.filter((x) => x !== branch),
    });

  return (
    <>
      <TabIntro>
        pr-mode multi-agent git workflow. <strong className="text-[var(--cos-text)]">Off by default</strong>
        {' '}— when enabled, agents isolate every change in a git worktree and integrate via PR +
        required CI (consumer-only; coding-os itself stays trunk). Enabling persists
        {' '}<span className="font-mono text-[11px]">COS_GIT_WORKFLOW=pr</span> into the agent env.
      </TabIntro>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-[var(--cos-faint)]">capability:</span>
        {!probeEnabled && <Pill tone="muted">enable pr-mode to probe</Pill>}
        {probeEnabled && stateLoading && <Pill tone="muted">checking…</Pill>}
        {probeEnabled && !stateLoading && stateError && !state && (
          <Pill tone="muted">unavailable — git/gh probe failed</Pill>
        )}
        {probeEnabled && state && (
          <>
            <Pill tone={state.remote ? 'ok' : 'muted'}>remote {state.remote ? '✓' : '—'}</Pill>
            <Pill tone={state.gh ? 'ok' : 'muted'}>gh {state.gh ? '✓' : '—'}</Pill>
            <Pill tone={state.required_check ? 'ok' : 'muted'}>required CI {state.required_check ? '✓' : '—'}</Pill>
            <Pill tone={state.pr_ok ? 'ok' : 'muted'}>{state.pr_ok ? 'pr-ready' : 'degrades to trunk'}</Pill>
          </>
        )}
      </div>

      {probeEnabled && state && (state.current_branch || state.remote_url) && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--cos-faint)]">
          {state.current_branch && (
            <span>
              current: <span className="font-mono text-[var(--cos-muted)]">{state.current_branch}</span>
            </span>
          )}
          {state.remote_url && (
            <span>
              remote: <span className="font-mono text-[var(--cos-muted)]">{state.remote_url}</span>
            </span>
          )}
          <span>{state.branches.length} branches</span>
        </div>
      )}

      <div className="space-y-4 rounded-xl border border-[var(--cos-border)] p-4">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="h-4 w-4 accent-[var(--cos-accent)] focus-visible:ring-2"
            aria-label="Enable pr-mode"
          />
          <span className="text-sm font-medium text-[var(--cos-text)]">Enable pr-mode</span>
        </label>

        <label className="block">
          <span className="text-xs font-medium text-[var(--cos-muted)]">Integration branch</span>
          {hasBranchList ? (
            <select
              value={form.integration_branch}
              onChange={(e) => setForm({ ...form, integration_branch: e.target.value })}
              className={inputClass}
              aria-label="Integration branch"
            >
              {(branches.includes(form.integration_branch)
                ? branches
                : [form.integration_branch, ...branches]
              ).map((b) => (
                <option key={b} value={b}>
                  {b}
                  {branches.includes(b) ? '' : ' (not in repo)'}
                </option>
              ))}
            </select>
          ) : (
            // Fallback when no branch list (pr-mode off / no repo) — free text.
            <input
              value={form.integration_branch}
              onChange={(e) => setForm({ ...form, integration_branch: e.target.value })}
              placeholder="main"
              className={inputClass}
            />
          )}
        </label>

        <div className="block">
          <span className="text-xs font-medium text-[var(--cos-muted)]">
            Protected branches (never agent-writable)
          </span>
          {hasBranchList ? (
            <div className="mt-1 max-h-40 space-y-1 overflow-auto rounded-md border border-[var(--cos-border)] p-2">
              {branches.map((b) => (
                <label key={b} className="flex items-center gap-2 text-sm text-[var(--cos-text)]">
                  <input
                    type="checkbox"
                    checked={form.protected_branches.includes(b)}
                    onChange={(e) => toggleProtected(b, e.target.checked)}
                    className="h-3.5 w-3.5 accent-[var(--cos-accent)] focus-visible:ring-2"
                  />
                  <span className="font-mono text-[12px]">{b}</span>
                </label>
              ))}
              {form.protected_branches
                .filter((b) => !branches.includes(b))
                .map((b) => (
                  <label key={b} className="flex items-center gap-2 text-sm text-[var(--cos-faint)]">
                    <input
                      type="checkbox"
                      checked
                      onChange={() => toggleProtected(b, false)}
                      className="h-3.5 w-3.5 accent-[var(--cos-accent)] focus-visible:ring-2"
                    />
                    <span className="font-mono text-[12px]">{b} (not in repo)</span>
                  </label>
                ))}
            </div>
          ) : (
            // Fallback when no branch list — comma-separated free text.
            <input
              value={form.protected_branches.join(', ')}
              onChange={(e) =>
                setForm({
                  ...form,
                  protected_branches: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              placeholder="production"
              className={inputClass}
            />
          )}
        </div>

        <label className="block">
          <span className="text-xs font-medium text-[var(--cos-muted)]">
            Autonomy level (Trust Spectrum — how far the agent acts unattended)
          </span>
          <select
            value={form.autonomy_level}
            onChange={(e) => setForm({ ...form, autonomy_level: e.target.value as AutonomyLevel })}
            className={inputClass}
            aria-label="Autonomy level"
          >
            {AUTONOMY_OPTIONS.map((opt) => {
              // Auto-discovery (TASK-540): a probe with no remote/gh disables the
              // push/PR rungs — but keep a saved-yet-now-unsupported value
              // selectable so a probe blip never silently rewrites the choice.
              const unavailable = !!state && opt.needsRemote && !state.pr_ok;
              return (
                <option
                  key={opt.value}
                  value={opt.value}
                  disabled={unavailable && opt.value !== form.autonomy_level}
                >
                  {opt.label}
                  {unavailable ? ' — needs remote + gh' : ''}
                </option>
              );
            })}
          </select>
          <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
            {AUTONOMY_OPTIONS.find((o) => o.value === form.autonomy_level)?.hint}
          </span>
          {state && !state.pr_ok && form.autonomy_level !== 'local' && (
            <p className="mt-1 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-400">
              This repo has no {!state.remote ? 'git remote' : 'gh auth'} — push/PR rungs
              degrade to trunk at submit. Use <span className="font-mono">Local</span>, or run{' '}
              <span className="font-mono">{!state.remote ? 'git remote add' : 'gh auth login'}</span>.
            </p>
          )}
          {state &&
            state.pr_ok &&
            !state.required_check &&
            (form.autonomy_level === 'auto_merge' || form.autonomy_level === 'autonomous') && (
              <p className="mt-1 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-400">
                No required status check on{' '}
                <span className="font-mono">{form.integration_branch}</span> — auto-merge will not
                arm; the PR stays open for manual merge. Add a required check, or use{' '}
                <span className="font-mono">Draft</span>/<span className="font-mono">Local</span>.
              </p>
            )}
        </label>

        {unknownBranches.length > 0 && (
          <p className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-400">
            Not in this repo: <span className="font-mono">{unknownBranches.join(', ')}</span> — double-check
            before saving.
          </p>
        )}

        {saveError && (
          <p role="alert" className="rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-400">
            {saveError}
          </p>
        )}

        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-1.5 text-sm text-[var(--cos-text)] hover:border-[var(--cos-accent)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </>
  );
}
