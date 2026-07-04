import type { ReactNode } from 'react';
import { useEffect, useId, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';
import { SubNav, subNavTabClass } from '@/layout/HubPrimitives';
import { useScopedLink } from '@/lib/use-scoped-link';

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
      <SubNav tablist ariaLabel="Configuration sections">
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
// InfoTip — accessible ⓘ popover. Opens on hover AND click/focus, closes on
// Esc, keyboard-reachable. Co-located here (the Git tab is its only consumer).
// --------------------------------------------------------------------------

function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const tipId = useId();
  // Esc dismisses even when opened by hover (the button isn't focused then) —
  // WCAG 1.4.13. Window-level so it fires regardless of focus (review finding 8).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={`What is ${label}?`}
        aria-describedby={open ? tipId : undefined}
        onClick={() => setOpen((v) => !v)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--cos-border)] text-[10px] font-semibold leading-none text-[var(--cos-faint)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          id={tipId}
          className="absolute left-0 top-5 z-20 w-72 rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-2 text-[11px] font-normal leading-relaxed text-[var(--cos-muted)] shadow-xl"
        >
          {children}
        </span>
      )}
    </span>
  );
}

// --------------------------------------------------------------------------
// Chip — small toggle/preset pill for branch selection (reused by both branch
// fields). `active` styles the selected state; plain `onClick` for one-shots.
// --------------------------------------------------------------------------

function Chip({
  active,
  onClick,
  children,
  ariaLabel,
}: {
  active?: boolean;
  onClick: () => void;
  children: ReactNode;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none ${
        active
          ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/15 text-[var(--cos-text)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:text-[var(--cos-text)]'
      }`}
    >
      {children}
    </button>
  );
}

// A field label with an inline InfoTip — used by every Git-tab control.
function FieldLabel({ label, tip }: { label: ReactNode; tip: ReactNode }) {
  const labelText = typeof label === 'string' ? label : 'this field';
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-xs font-medium text-[var(--cos-muted)]">{label}</span>
      <InfoTip label={labelText}>{tip}</InfoTip>
    </span>
  );
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
  hint?: string;
  kernel: boolean;
  enabled: boolean;
  depends_on: string[];
  hooks: number;
  tools: number;
  skills: number;
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
  const [notes, setNotes] = useState<string[]>([]);
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

  // Reverse dependency edges, derived from the rows the API already returns —
  // so the table SHOWS "what depends on this" and greys out a disable the
  // backend would refuse, instead of surfacing a raw refusal only after a click.
  const dependentsOf = (id: string) => rows.filter((r) => r.depends_on.includes(id)).map((r) => r.id);
  const enabledDependentsOf = (id: string) =>
    rows.filter((r) => r.enabled && r.depends_on.includes(id)).map((r) => r.id);
  const disabledDepsOf = (m: ModuleRow) =>
    m.depends_on.filter((d) => rows.some((r) => r.id === d && !r.enabled));

  const toggle = async (row: ModuleRow) => {
    setBusyId(row.id);
    setToggleError(null);
    setNotes([]);
    try {
      const [data] = await apiPatch<{ regenerated?: string[] }>(
        `/api/settings/modules/${encodeURIComponent(row.id)}`,
        { enabled: !row.enabled },
      );
      setNotes(data?.regenerated ?? []);
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
      {notes.length > 0 && (
        <div className="mb-3 rounded border border-[var(--cos-border)] bg-white/[0.02] p-2 text-xs text-[var(--cos-muted)]">
          <div className="flex items-center justify-between">
            <span className="font-medium text-[var(--cos-text)]">Applied ({notes.length})</span>
            <button
              type="button"
              onClick={() => setNotes([])}
              className="text-[10px] text-[var(--cos-faint)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
            >
              dismiss
            </button>
          </div>
          <ul className="mt-1 list-disc pl-4">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      <Table head={['Module', 'State', 'Owns', 'Depends on', 'Required by', '']}>
        {rows.map((m) => {
          const dependents = dependentsOf(m.id);
          const blockedBy = enabledDependentsOf(m.id);
          const missingDeps = disabledDepsOf(m);
          const disableBlocked = m.enabled && blockedBy.length > 0;
          const enableBlocked = !m.enabled && missingDeps.length > 0;
          const blockedReason = disableBlocked
            ? `Required by ${blockedBy.join(', ')} — disable ${blockedBy.length > 1 ? 'them' : 'it'} first`
            : enableBlocked
              ? `Needs ${missingDeps.join(', ')} — enable ${missingDeps.length > 1 ? 'them' : 'it'} first`
              : undefined;
          return (
            <tr key={m.id} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
              <td className="px-3 py-2">
                <div className="font-medium text-[var(--cos-text)]">{m.id}</div>
                <div className="text-[10px] text-[var(--cos-faint)]">{m.label}</div>
                {m.hint && (
                  <div className="mt-0.5 max-w-md text-[10px] leading-snug text-[var(--cos-muted)]">{m.hint}</div>
                )}
              </td>
              <td className="px-3 py-2">
                {m.kernel ? (
                  <Pill tone="muted">kernel · locked</Pill>
                ) : (
                  <Pill tone={m.enabled ? 'ok' : 'muted'}>{m.enabled ? 'enabled' : 'disabled'}</Pill>
                )}
              </td>
              <td className="px-3 py-2 text-[var(--cos-muted)]">
                {m.hooks} hooks · {m.tools} tools · {m.skills} skills
              </td>
              <td className="px-3 py-2 text-[var(--cos-faint)]">{m.depends_on.join(', ') || '—'}</td>
              <td className="px-3 py-2 text-[var(--cos-faint)]">{dependents.join(', ') || '—'}</td>
              <td className="px-3 py-2 text-right">
                {!m.kernel && (
                  <button
                    type="button"
                    data-testid={`module-toggle-${m.id}`}
                    onClick={() => void toggle(m)}
                    disabled={busyId !== null || disableBlocked || enableBlocked}
                    title={blockedReason}
                    aria-pressed={m.enabled}
                    className="rounded border border-[var(--cos-border)] px-2.5 py-1 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
                  >
                    {busyId === m.id ? '…' : m.enabled ? 'Disable' : 'Enable'}
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </Table>
    </>
  );
}

// --------------------------------------------------------------------------
// Git — pr-mode multi-agent workflow (settings-gated, default OFF). TASK-518.
// Project-scoped config (each project has its own hub-settings.json), so it
// lives in Config, not the hub-level Settings page where model_routing sits.
// --------------------------------------------------------------------------

type AutonomyLevel = 'local' | 'local_autonomous' | 'draft' | 'auto_merge' | 'autonomous';

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
  { value: 'local', label: 'Local — never pushes', hint: 'Commits locally, never pushes; you review & merge. Also auto-commits board churn on trunk. Works with no remote.', needsRemote: false },
  { value: 'local_autonomous', label: 'Local autonomous — commits + lands locally', hint: 'Commits and lands on the local integration branch after a green verify; zero network. Drives trunk board-churn auto-commit.', needsRemote: false },
  { value: 'draft', label: 'Draft — opens a PR', hint: 'Pushes + opens a PR; you merge it. Needs a remote + GitHub.', needsRemote: true },
  { value: 'auto_merge', label: 'Auto-merge — merges on green CI', hint: 'Pushes, opens a PR, merges itself once required CI passes. Needs a required status check.', needsRemote: true },
  { value: 'autonomous', label: 'Autonomous — hands-off', hint: 'Auto-merge + cleans up its own worktree & branch after merge.', needsRemote: true },
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

// The meta-repo's own derived slug (cli.registry._derive_slug). coding-os
// ships trunk by default (ADR-0013); the Git tab stays fully editable but
// shows one caution on this slug (enabling pr-mode flips the mother repo).
const META_REPO_SLUG = 'coding-os';

// One-click quick starts. A preset only fills the form (setForm) — the user
// reviews and Saves; the global default stays OFF. `recommended` flags the
// multi-agent happy path with an accent badge.
const QUICK_START_PRESETS: {
  id: string;
  label: string;
  recommended?: boolean;
  blurb: string;
  apply: Pick<GitSettings, 'enabled' | 'integration_branch' | 'protected_branches' | 'autonomy_level'>;
}[] = [
  {
    id: 'solo-local',
    label: 'Solo / local',
    blurb: 'One agent, or no GitHub. Agents isolate in worktrees; you review & merge. Works with no remote.',
    apply: { enabled: true, integration_branch: 'main', protected_branches: [], autonomy_level: 'local' },
  },
  {
    id: 'team-github-ci',
    label: 'Team + GitHub CI',
    recommended: true,
    blurb: 'Agents open PRs into main and auto-merge once CI is green.',
    apply: { enabled: true, integration_branch: 'main', protected_branches: ['production'], autonomy_level: 'auto_merge' },
  },
  {
    id: 'main-dev-prod',
    label: 'main → dev → prod',
    blurb: 'Agents integrate to develop; main + production are human-only.',
    apply: { enabled: true, integration_branch: 'develop', protected_branches: ['main', 'production'], autonomy_level: 'auto_merge' },
  },
];

// Per-field info copy (what + how) — paraphrases pr-workflow.md.
const FIELD_TIPS = {
  enabled:
    'Multi-agent safety mode. Each agent works in its own isolated git worktree (under ~/.coding-os/worktrees) and lands changes via a Pull Request — so 5+ agents never overwrite or block each other. Off = trunk: agents commit straight to the branch (fine for one agent, risky for many).',
  integration_branch:
    'The branch agents merge their work into, via PR — they branch off it and target it. Usually main or develop. It stays always-green: broken code can’t reach it because CI gates the merge.',
  protected_branches:
    'Branches agents may NEVER write, push, or merge to — human-only (e.g. production). Exact names and shell-style patterns such as release/* are enforced by branch-guard. Leave empty if you have none.',
  autonomy_level:
    'How far an agent acts without you. Local: commits only, you merge. Draft: opens a PR, you click merge. Auto-merge: merges itself when CI is green. Autonomous: also cleans up after itself. Higher rungs need a remote + GitHub gh today. CI always gates the merge — autonomy changes who clicks merge, never whether code is checked.',
};

// Common branch presets for the no-branch-list fallback chips.
const INTEGRATION_BRANCH_CHIPS = ['main', 'develop', 'master'];
const PROTECTED_BRANCH_CHIPS = ['production', 'main', 'release/*'];

const inputClass =
  'mt-1 w-full rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-2.5 py-1.5 text-sm text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none';

const isBranchPattern = (branch: string) =>
  branch.includes('*') || branch.includes('?') || branch.includes('[');

function GitTab() {
  const qc = useQueryClient();
  // coding-os ships trunk by default (ADR-0013), but the tab stays fully
  // editable on every project — the trunk default is the saved enabled=false,
  // not a hidden UI. On the meta-repo we surface one caution about the
  // consequence of enabling (it would switch the mother repo off trunk).
  const { slug } = useScopedLink();
  const isMetaRepo = slug === META_REPO_SLUG;
  const { data, isLoading, error } = useApiGet<{ settings: { git_settings: GitSettings } }>(
    ['settings-git'],
    '/api/settings',
  );
  const loaded = data?.settings?.git_settings;
  const [form, setForm] = useState<GitSettings | null>(null);
  // Custom-branch add inputs for the no-branch-list fallback (controlled).
  const [customProtected, setCustomProtected] = useState('');
  // Probe whenever the Git tab is open (NOT gated on `enabled`) so the capability
  // pills + branch list are visible BEFORE the user commits to enabling — a user
  // must not configure blind then discover at submit the repo can't do pr-mode (M8).
  // Probe the branch being selected, keyed by it, so switching the dropdown
  // refetches required_check / pr_ok for THAT branch; staleTime caches per-branch.
  const probeBranch = (form?.integration_branch ?? loaded?.integration_branch ?? 'main').trim() || 'main';
  const {
    data: state,
    isLoading: stateLoading,
    error: stateError,
  } = useApiGet<GitState>(
    ['settings-git-state', probeBranch],
    '/api/settings/git-state',
    { integration: probeBranch },
    { enabled: true, staleTimeMs: 60_000 },
  );

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmEnable, setConfirmEnable] = useState(false);
  // Seed the form once when settings arrive; deps gate the effect so it never loops.
  useEffect(() => {
    if (loaded && form === null) setForm(loaded);
  }, [loaded, form]);

  if (isLoading) return <StateRow>Loading git settings…</StateRow>;
  if (error) return <StateRow>Could not load git settings: {error.message}</StateRow>;
  if (!form) return <StateRow>Loading…</StateRow>;

  // First transition saved-disabled → enabled is the irreversible, wide-blast-radius
  // change (git-workflow.md) — gate it behind an explicit confirm step (H5).
  const willEnable = form.enabled && !loaded?.enabled;

  const save = async () => {
    if (isMetaRepo && form.enabled) {
      setSaveError(
        'pr-mode cannot be enabled on coding-os — the meta-repo stays trunk (ADR-0013). Enable it on a consumer project instead.',
      );
      return;
    }
    if (willEnable && !confirmEnable) {
      setConfirmEnable(true);
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const [resp] = await apiPatch<{ settings: { git_settings: GitSettings } }>('/api/settings', {
        git_settings: {
          enabled: form.enabled,
          integration_branch: form.integration_branch.trim() || 'main',
          protected_branches: form.protected_branches,
          autonomy_level: form.autonomy_level,
        },
      });
      // Re-seed from the server-confirmed response so the form shows persisted
      // truth (incl. any coercion), not the local pre-save state (M7).
      if (resp?.settings?.git_settings) setForm(resp.settings.git_settings);
      await invalidateApiQueries(qc, 'settings-git');
      await invalidateApiQueries(qc, 'settings-git-state');
      setConfirmEnable(false);
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
    ? [
        ...(branches.includes(form.integration_branch.trim())
          ? []
          : [form.integration_branch.trim()].filter(Boolean)),
        ...form.protected_branches
          .map((b) => b.trim())
          .filter((b) => b && !isBranchPattern(b) && !branches.includes(b)),
      ]
    : [];
  const toggleProtected = (branch: string, on: boolean) =>
    setForm({
      ...form,
      protected_branches: on
        ? [...form.protected_branches, branch]
        : form.protected_branches.filter((x) => x !== branch),
    });
  const isProtected = (branch: string) => form.protected_branches.includes(branch);
  const toggleProtectedChip = (branch: string) => toggleProtected(branch, !isProtected(branch));
  const clearProtected = () => setForm({ ...form, protected_branches: [] });
  const addCustomProtected = () => {
    const value = customProtected.trim();
    if (value && !isProtected(value)) toggleProtected(value, true);
    setCustomProtected('');
  };
  // On the meta-repo a preset must not flip `enabled` on — pr-mode is hard-blocked
  // there (the mother stays trunk); the preset's branch/autonomy choices still apply.
  const applyPreset = (apply: GitSettings) =>
    setForm({ ...form, ...apply, enabled: isMetaRepo ? false : apply.enabled });
  // Selected look keys on "matches the current form", NOT `recommended` — so the
  // Recommended card isn't pre-selected and a clicked preset reads as chosen.
  const sameSet = (a: string[], b: string[]) =>
    a.length === b.length && [...a].sort().join('\u0000') === [...b].sort().join('\u0000');
  const isPresetActive = (apply: GitSettings) =>
    form.enabled === apply.enabled &&
    // normalize the integration branch the same way save() does, so a raw-typed
    // value with stray whitespace still matches its preset.
    (form.integration_branch.trim() || 'main') === (apply.integration_branch.trim() || 'main') &&
    form.autonomy_level === apply.autonomy_level &&
    sameSet(form.protected_branches, apply.protected_branches);

  return (
    <>
      <TabIntro>
        pr-mode multi-agent git workflow. <strong className="text-[var(--cos-text)]">Off by default</strong>
        {' '}— when enabled, agents isolate every change in its own git worktree and land it via a Pull
        Request, so many agents never overwrite or block each other. Pick a quick start below, or set
        each field by hand — then Save.
      </TabIntro>

      {isMetaRepo && (
        <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-[var(--cos-muted)]">
          <strong className="text-[var(--cos-text)]">You’re viewing coding-os, the meta-repo.</strong>{' '}
          It ships trunk by default — enabling pr-mode here switches the mother repo off trunk. pr-mode
          is meant for your consumer projects; the tab is fully editable, just enable it where you
          intend to run agents.
        </div>
      )}

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-[var(--cos-faint)]">capability:</span>
        {stateLoading && <Pill tone="muted">checking…</Pill>}
        {!stateLoading && stateError && !state && (
          <Pill tone="muted">unavailable — git/gh probe failed</Pill>
        )}
        {state && (
          <>
            <Pill tone={state.remote ? 'ok' : 'muted'}>remote {state.remote ? '✓' : '—'}</Pill>
            <Pill tone={state.gh ? 'ok' : 'muted'}>gh {state.gh ? '✓' : '—'}</Pill>
            <Pill tone={state.required_check ? 'ok' : 'muted'}>required CI {state.required_check ? '✓' : '—'}</Pill>
            <Pill tone={state.pr_ok ? 'ok' : 'muted'}>
              {state.pr_ok ? 'pr-ready' : 'PR publish unavailable'}
            </Pill>
          </>
        )}
      </div>

      {state && (state.current_branch || state.remote_url) && (
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

      <div className="mb-4">
        <span className="text-xs font-medium text-[var(--cos-muted)]">Quick start</span>
        <p className="mb-2 text-[11px] text-[var(--cos-faint)]">
          One click fills the form below — review it, then Save. A preset never changes the global
          default (which stays Off).
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {QUICK_START_PRESETS.map((preset) => {
            const active = isPresetActive(preset.apply);
            return (
              <button
                key={preset.id}
                type="button"
                aria-pressed={active}
                onClick={() => applyPreset(preset.apply)}
                className={`rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none ${
                  active
                    ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 hover:bg-[var(--cos-accent)]/15'
                    : 'border-[var(--cos-border)] hover:border-[var(--cos-accent)]'
                }`}
              >
                <span className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-[var(--cos-text)]">{preset.label}</span>
                  {preset.recommended && (
                    <span className="rounded-full bg-[var(--cos-accent)]/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[var(--cos-accent)]">
                      ★ Recommended
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-[11px] leading-relaxed text-[var(--cos-muted)]">
                  {preset.blurb}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-4 rounded-xl border border-[var(--cos-border)] p-4">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={form.enabled}
            disabled={isMetaRepo}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="h-4 w-4 accent-[var(--cos-accent)] focus-visible:ring-2 disabled:opacity-40"
            aria-label="Enable pr-mode"
          />
          <span className="text-sm font-medium text-[var(--cos-text)]">Enable pr-mode</span>
          <InfoTip label="Enable pr-mode">{FIELD_TIPS.enabled}</InfoTip>
        </label>
        <div className="space-y-1 text-[11px] text-[var(--cos-faint)]">
          {isMetaRepo && <p>Disabled on coding-os — the meta-repo stays trunk (ADR-0013).</p>}
          <p>
            Agent-layer only: Claude gets edit + git guards; Codex gets Bash/git guards, so shared-tree
            edits can still happen, but shared-tree commits/pushes are blocked. Human/plain git is outside
            this hook wall; repo git hooks cover content and commit messages only.
          </p>
        </div>

        <label className="block">
          <FieldLabel label="Integration branch" tip={FIELD_TIPS.integration_branch} />
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
            // Fallback when no branch list (pr-mode off / no repo) — quick chips
            // pick a common branch, free typing covers the rest. Never empty.
            <>
              <input
                value={form.integration_branch}
                onChange={(e) => setForm({ ...form, integration_branch: e.target.value })}
                placeholder="main"
                className={inputClass}
                aria-label="Integration branch"
              />
              <span className="mt-1.5 flex flex-wrap gap-1.5">
                {INTEGRATION_BRANCH_CHIPS.map((b) => (
                  <Chip
                    key={b}
                    active={form.integration_branch.trim() === b}
                    ariaLabel={`Set integration branch to ${b}`}
                    onClick={() => setForm({ ...form, integration_branch: b })}
                  >
                    {b}
                  </Chip>
                ))}
              </span>
            </>
          )}
          <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
            Agents branch off this and open PRs back into it. Defaults to{' '}
            <span className="font-mono">main</span>.
          </span>
        </label>

        <div className="block">
          <span className="flex items-center justify-between">
            <FieldLabel label="Protected branches" tip={FIELD_TIPS.protected_branches} />
            <button
              type="button"
              onClick={clearProtected}
              disabled={form.protected_branches.length === 0}
              className="rounded border border-[var(--cos-border)] px-2 py-0.5 text-[10px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none disabled:opacity-40"
            >
              None
            </button>
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
                    <span className="font-mono text-[12px]">
                      {b} {isBranchPattern(b) ? '(pattern)' : '(not in repo)'}
                    </span>
                  </label>
                ))}
            </div>
          ) : (
            // Fallback when no branch list — common toggle chips + custom add.
            <span className="mt-1 flex flex-wrap gap-1.5">
              {[...PROTECTED_BRANCH_CHIPS, ...form.protected_branches.filter((b) => !PROTECTED_BRANCH_CHIPS.includes(b))].map(
                (b) => (
                  <Chip
                    key={b}
                    active={isProtected(b)}
                    ariaLabel={`${isProtected(b) ? 'Unprotect' : 'Protect'} ${b}`}
                    onClick={() => toggleProtectedChip(b)}
                  >
                    {b}
                  </Chip>
                ),
              )}
            </span>
          )}
          <span className="mt-2 flex gap-1.5">
            <input
              value={customProtected}
              onChange={(e) => setCustomProtected(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addCustomProtected();
                }
              }}
              placeholder="add a branch…"
              aria-label="Add protected branch"
              className="flex-1 rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-2.5 py-1 text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none"
            />
            <button
              type="button"
              onClick={addCustomProtected}
              disabled={!customProtected.trim()}
              className="rounded-md border border-[var(--cos-border)] px-2.5 py-1 text-xs text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none disabled:opacity-40"
            >
              Add
            </button>
          </span>
          <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
            {form.protected_branches.length === 0
              ? 'None — no protected branches.'
              : `Human-only: ${form.protected_branches.join(', ')}`}
          </span>
          <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
            Exact names and patterns are enforced; <span className="font-mono">release/*</span> covers{' '}
            <span className="font-mono">release/v1</span>, not{' '}
            <span className="font-mono">release-candidate</span>.
          </span>
        </div>

        <label className="block">
          <FieldLabel
            label="Autonomy level"
            tip={FIELD_TIPS.autonomy_level}
          />
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
          <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
            Draft, auto-merge, and autonomous publish through GitHub{' '}
            <span className="font-mono">gh</span> today. GitLab, Gitea, Forgejo,
            Bitbucket, and self-hosted forges use <span className="font-mono">Local</span>.
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

        {confirmEnable && (
          <div
            role="alertdialog"
            aria-label="Confirm enabling pr-mode"
            className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-[11px] leading-relaxed text-[var(--cos-muted)]"
          >
            <p className="text-[var(--cos-text)]">
              Enabling pr-mode switches this project off trunk: agents will isolate every change in its
              own git worktree and land it via a Pull Request. You can switch back by disabling it.
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className="rounded-md border border-amber-500/50 bg-amber-500/15 px-3 py-1.5 text-amber-300 hover:bg-amber-500/25 focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
              >
                {saving ? 'Enabling…' : 'Confirm enable'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmEnable(false)}
                disabled={saving}
                className="rounded-md border border-[var(--cos-border)] px-3 py-1.5 text-[var(--cos-muted)] hover:border-[var(--cos-accent)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || confirmEnable}
          className="rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-1.5 text-sm text-[var(--cos-text)] hover:border-[var(--cos-accent)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
        >
          {saving ? 'Saving…' : willEnable ? 'Enable pr-mode…' : 'Save'}
        </button>
      </div>
    </>
  );
}
