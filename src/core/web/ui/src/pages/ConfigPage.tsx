import type { ReactNode } from 'react';
import { useEffect, useId, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronRight, Lock, Plus, Trash2 } from 'lucide-react';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiDelete, apiPatch, apiPost } from '@/lib/api-client';
import { Banner, SubNav, subNavTabClass } from '@/layout/HubPrimitives';
import { useScopedLink } from '@/lib/use-scoped-link';

/**
 * Per-project Configuration surface. Shows what tech stacks, skills, MCP
 * servers, hooks, and modules are wired for the active project so a human can
 * SEE the setup without reading YAML/JSON. Modules and extra skills ARE
 * toggleable here (subsystems-state.json / .coding-os.yaml); stacks, MCP, and
 * hooks stay read-only — per-project enable/disable for those is a separate
 * kernel-override epic (a toggle must never edit the global registry).
 */

type Tab = 'stacks' | 'skills' | 'mcp' | 'adapters' | 'hooks' | 'modules' | 'git';
const TABS: Tab[] = ['stacks', 'skills', 'mcp', 'adapters', 'hooks', 'modules', 'git'];
const TAB_LABEL: Record<Tab, string> = {
  stacks: 'Stacks',
  skills: 'Skills',
  mcp: 'MCP Servers',
  adapters: 'Adapters',
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
          {tab === 'adapters' && <AdaptersTab />}
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
// Config mutation chrome. The meta-repo ships every stack/adapter as a template
// and installs none in the consumer sense, so install/remove is disabled on its
// slug — parity with the Git-tab trunk caution.
// --------------------------------------------------------------------------

// The meta-repo's own derived slug (cli.registry._derive_slug). Mutations are
// disabled on this slug; the Git tab keys its trunk caution off the same value.
const META_REPO_SLUG = 'coding-os';

function useConfigMutation(invalidate: string[]) {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(id: string, fn: () => Promise<T>): Promise<T | null> => {
    setBusyId(id);
    setError(null);
    try {
      const out = await fn();
      for (const key of invalidate) await invalidateApiQueries(qc, key);
      return out;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'operation failed');
      return null;
    } finally {
      setBusyId(null);
    }
  };
  return { busyId, error, setError, run };
}

function SectionCard({
  title,
  subtitle,
  count,
  action,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  count?: number;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-5 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40">
      <header className="flex items-center justify-between gap-3 border-b border-[var(--cos-border)] px-4 py-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--cos-text)]">
            {title}
            {typeof count === 'number' && (
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-normal text-[var(--cos-muted)]">
                {count}
              </span>
            )}
          </h3>
          {subtitle && (
            <p className="mt-0.5 max-w-2xl text-[11px] leading-relaxed text-[var(--cos-faint)]">{subtitle}</p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className="divide-y divide-[var(--cos-border)]">{children}</div>
    </section>
  );
}

function ConfigRow({
  title,
  badges,
  meta,
  action,
}: {
  title: ReactNode;
  badges?: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-white/[0.02]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium text-[var(--cos-text)]">{title}</span>
          {badges}
        </div>
        {meta && <div className="mt-0.5 text-[11px] leading-relaxed text-[var(--cos-faint)]">{meta}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

function EmptyRow({ children }: { children: ReactNode }) {
  return <p className="px-4 py-6 text-center text-[13px] text-[var(--cos-muted)]">{children}</p>;
}

function CfgButton({
  tone = 'ghost',
  busy,
  disabled,
  onClick,
  icon,
  title,
  ariaPressed,
  children,
}: {
  tone?: 'primary' | 'ghost' | 'danger';
  busy?: boolean;
  disabled?: boolean;
  onClick: () => void;
  icon?: ReactNode;
  title?: string;
  ariaPressed?: boolean;
  children: ReactNode;
}) {
  const palette =
    tone === 'primary'
      ? 'border-transparent bg-[var(--cos-accent)] text-white hover:opacity-90'
      : tone === 'danger'
        ? 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-err)] hover:text-[var(--cos-err)]'
        : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-accent)] hover:text-[var(--cos-text)]';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      title={title}
      aria-pressed={ariaPressed}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:cursor-not-allowed disabled:opacity-40 ${palette}`}
    >
      {busy ? <span className="animate-pulse">…</span> : icon}
      {children}
    </button>
  );
}

function MetaCaution({ what }: { what: string }) {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-[var(--cos-muted)]">
      <Lock size={13} aria-hidden className="mt-0.5 shrink-0 text-amber-400" />
      <span>
        <strong className="text-[var(--cos-text)]">This is coding-os, the meta-repo.</strong> It ships every{' '}
        {what} as a template and installs none in the consumer sense — {what} management is disabled here.
        Open a consumer project to add or remove.
      </span>
    </div>
  );
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
  const { slug } = useScopedLink();
  const metaRepo = slug === META_REPO_SLUG;
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
      {metaRepo && <MetaCaution what="stack" />}
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
            disabled={metaRepo}
            title={metaRepo ? 'Disabled on the meta-repo' : undefined}
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
                  disabled={metaRepo || (busyId !== null && busyId !== s.id)}
                  title={metaRepo ? 'Disabled on the meta-repo' : `Remove ${s.label || s.id}`}
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
      {showAdd && !metaRepo && (
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

interface SkillRow {
  name: string;
  tier: string;
  domain: string[];
  globs: string | null;
  description?: string;
  extra?: boolean;
  // Producer fields (config_skills): provenance ("core" / "stack:<id>") + disabled
  // let the Hub Enable/Disable a core/stack skill; `stacks` is the installed
  // stacks that use it, powering the grouped-by-stack view.
  provenance?: string;
  disabled?: boolean;
  stacks?: string[];
}

interface InstalledStack {
  id: string;
  label: string;
}

function ProvenanceBadge({ skill }: { skill: SkillRow }) {
  if (skill.extra) return <Pill tone="ok">yours</Pill>;
  const prov = skill.provenance ?? 'core';
  if (prov.startsWith('stack:')) return <Pill tone="muted">{prov.slice('stack:'.length)}</Pill>;
  return <Pill tone="muted">core</Pill>;
}

function SkillsTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ skills: SkillRow[]; installed_stacks: InstalledStack[] }>(
    ['config-skills'],
    '/api/config/skills',
  );
  const [pending, setPending] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  if (isLoading) return <StateRow>Loading skills…</StateRow>;
  if (error) return <StateRow>Could not load skills: {error.message}</StateRow>;
  const rows = data?.skills ?? [];
  const installedStacks = data?.installed_stacks ?? [];

  // Core/stack skills ship by default → Enable/Disable via disabled_skills.
  // The PATCH route (set_project_skill) routes by provenance; the UI sends intent.
  const isCoreStack = (s: SkillRow) => {
    const prov = s.provenance ?? 'core';
    return prov === 'core' || prov.startsWith('stack:');
  };
  const toggle = async (skill: SkillRow) => {
    setPending(skill.name);
    try {
      const nextEnabled = isCoreStack(skill) ? !!skill.disabled : !skill.extra;
      await apiPatch(`/api/config/skills/${skill.name}`, { enabled: nextEnabled });
      await invalidateApiQueries(qc, 'config-skills');
    } finally {
      setPending(null);
    }
  };
  const actionVerb = (s: SkillRow) => (s.extra ? 'Remove' : s.disabled ? 'Enable' : 'Disable');
  const actionTone = (s: SkillRow): 'primary' | 'ghost' | 'danger' =>
    s.extra ? 'danger' : s.disabled ? 'primary' : 'ghost';

  const skillRow = (s: SkillRow) => (
    <ConfigRow
      key={s.name}
      title={<span className={s.disabled ? 'text-[var(--cos-faint)]' : undefined}>{s.name}</span>}
      badges={
        <>
          <ProvenanceBadge skill={s} />
          {!s.extra && (
            <span
              className={`text-[10px] font-medium ${s.disabled ? 'text-[var(--cos-faint)]' : 'text-[var(--cos-ok)]'}`}
            >
              {s.disabled ? 'off' : 'on'}
            </span>
          )}
        </>
      }
      meta={
        <>
          {s.tier}
          {s.domain.length > 0 && <> · {s.domain.join(', ')}</>}
          {s.globs && (
            <>
              {' · '}
              <span className="font-mono text-[10px]">{s.globs}</span>
            </>
          )}
        </>
      }
      action={
        <CfgButton
          tone={actionTone(s)}
          busy={pending === s.name}
          disabled={pending !== null && pending !== s.name}
          ariaPressed={s.extra ? undefined : !s.disabled}
          onClick={() => void toggle(s)}
          title={`${actionVerb(s)} ${s.name}`}
        >
          {actionVerb(s)}
        </CfgButton>
      }
    />
  );

  const prov = (s: SkillRow) => s.provenance ?? 'core';
  const shippedBy = (sid: string) => rows.filter((s) => s.provenance === `stack:${sid}` && !s.extra);
  const coreActive = rows.filter((s) => prov(s) === 'core' && (s.stacks?.length ?? 0) > 0 && !s.extra);
  const yourSkills = rows.filter((s) => s.extra);
  const moreAvailable = rows.filter((s) => prov(s) === 'core' && (s.stacks?.length ?? 0) === 0 && !s.extra);

  return (
    <>
      <TabIntro>
        The skills active in this project, grouped by the stack that uses them. Skills are glob-gated — the
        agent loads one automatically before editing matching files. Disable one to drop it for this project.
      </TabIntro>

      {installedStacks.map((stack) => {
        const shipped = shippedBy(stack.id);
        if (shipped.length === 0) return null;
        return (
          <SectionCard
            key={stack.id}
            title={`${stack.label} skills`}
            count={shipped.length}
            subtitle="Shipped by this stack."
          >
            {shipped.map(skillRow)}
          </SectionCard>
        );
      })}

      {coreActive.length > 0 && (
        <SectionCard
          title="Core skills · active"
          count={coreActive.length}
          subtitle="Kernel skills your installed stacks rely on."
        >
          {coreActive.map(skillRow)}
        </SectionCard>
      )}

      {yourSkills.length > 0 && (
        <SectionCard title="Your skills" count={yourSkills.length} subtitle="Added beyond the stacks.">
          {yourSkills.map(skillRow)}
        </SectionCard>
      )}

      {moreAvailable.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            aria-expanded={showMore}
            className="mb-3 flex items-center gap-1.5 rounded-lg border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            <ChevronRight
              size={13}
              aria-hidden
              className={`transition-transform ${showMore ? 'rotate-90' : ''}`}
            />
            {showMore ? 'Hide' : 'Show'} {moreAvailable.length} more available core skills
          </button>
          {showMore && (
            <SectionCard
              title="More available"
              count={moreAvailable.length}
              subtitle="Core skills not used by an installed stack. They still load on matching files — disable one to drop it from this project."
            >
              {moreAvailable.map(skillRow)}
            </SectionCard>
          )}
        </>
      )}
    </>
  );
}

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

function McpTab() {
  const { slug } = useScopedLink();
  const metaRepo = slug === META_REPO_SLUG;
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
      {metaRepo && <MetaCaution what="MCP server" />}
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
            disabled={metaRepo}
            title={metaRepo ? 'Disabled on the meta-repo' : undefined}
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
                    disabled={metaRepo || (busyId !== null && busyId !== s.name)}
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
      {showAdd && !metaRepo && (
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

interface AdapterModel {
  id: string;
  label: string;
  default: boolean;
}

interface AdapterRow {
  id: string;
  label: string;
  runtime: string;
  available: boolean;
  installed: boolean;
  glyph?: string | null;
  models: AdapterModel[];
  mcp_config_paths: string[];
}

function AdaptersTab() {
  const { slug } = useScopedLink();
  const metaRepo = slug === META_REPO_SLUG;
  const { data, isLoading, error } = useApiGet<{ adapters: AdapterRow[]; default_model: string }>(
    ['config-adapters'],
    '/api/config/adapters',
  );
  const { busyId, error: mutError, setError, run } = useConfigMutation(['config-adapters']);
  const [showAdd, setShowAdd] = useState(false);
  if (isLoading) return <StateRow>Loading adapters…</StateRow>;
  if (error) return <StateRow>Could not load adapters: {error.message}</StateRow>;
  const all = data?.adapters ?? [];
  const installed = all.filter((a) => a.installed);
  const addable = all.filter((a) => !a.installed);
  const defaultModel = data?.default_model ?? '';
  const add = (id: string) => run(id, () => apiPost(`/api/config/adapters/${id}`));
  const remove = (id: string) => run(id, () => apiDelete(`/api/config/adapters/${id}`));
  const glyphBox = (a: AdapterRow) =>
    a.glyph ? (
      <span className="inline-flex h-5 w-5 items-center justify-center rounded border border-[var(--cos-border)] font-mono text-[10px] text-[var(--cos-muted)]">
        {a.glyph}
      </span>
    ) : null;
  const adapterMeta = (a: AdapterRow) => (
    <>
      <span className="font-mono">{a.id}</span>
      {a.mcp_config_paths.length > 0 && (
        <>
          {' · MCP → '}
          <span className="font-mono">{a.mcp_config_paths.join(', ')}</span>
        </>
      )}
      {a.models.length > 0 && (
        <div className="mt-0.5">
          {a.models.map((m) => `${m.label}${m.default ? ' (default)' : ''}`).join(', ')}
        </div>
      )}
    </>
  );
  return (
    <>
      <TabIntro>
        The agent adapters wired for this project. The runnable one (in_process) drives Hub chat; a roadmap
        adapter is declared but not yet runnable here. Add another to run more than one agent side by side.
      </TabIntro>
      {metaRepo && <MetaCaution what="adapter" />}
      {mutError && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {mutError}
        </Banner>
      )}
      <SectionCard
        title="Installed"
        count={installed.length}
        action={
          addable.length > 0 ? (
            <CfgButton
              tone="primary"
              icon={<Plus size={13} aria-hidden />}
              disabled={metaRepo}
              title={metaRepo ? 'Disabled on the meta-repo' : undefined}
              onClick={() => setShowAdd((v) => !v)}
            >
              Add adapter
            </CfgButton>
          ) : undefined
        }
      >
        {installed.length === 0 ? (
          <EmptyRow>No adapters installed.</EmptyRow>
        ) : (
          installed.map((a) => (
            <ConfigRow
              key={a.id}
              title={
                <span className="inline-flex items-center gap-2">
                  {glyphBox(a)}
                  {a.label || a.id}
                </span>
              }
              badges={<Pill tone={a.available ? 'ok' : 'muted'}>{a.runtime}</Pill>}
              meta={adapterMeta(a)}
              action={
                <CfgButton
                  tone="danger"
                  busy={busyId === a.id}
                  disabled={metaRepo || installed.length <= 1 || (busyId !== null && busyId !== a.id)}
                  title={
                    metaRepo
                      ? 'Disabled on the meta-repo'
                      : installed.length <= 1
                        ? 'A project needs at least one adapter'
                        : `Remove ${a.label || a.id}`
                  }
                  onClick={() => remove(a.id)}
                  icon={<Trash2 size={13} aria-hidden />}
                >
                  Remove
                </CfgButton>
              }
            />
          ))
        )}
      </SectionCard>
      {showAdd && !metaRepo && addable.length > 0 && (
        <SectionCard
          title="Available to add"
          count={addable.length}
          subtitle="Adding an adapter runs its install.sh and renders its per-agent surface."
        >
          {addable.map((a) => (
            <ConfigRow
              key={a.id}
              title={
                <span className="inline-flex items-center gap-2">
                  {glyphBox(a)}
                  {a.label || a.id}
                </span>
              }
              badges={<Pill tone={a.available ? 'ok' : 'muted'}>{a.runtime}</Pill>}
              meta={adapterMeta(a)}
              action={
                <CfgButton
                  tone="primary"
                  busy={busyId === a.id}
                  disabled={busyId !== null && busyId !== a.id}
                  onClick={() => add(a.id)}
                  icon={<Plus size={13} aria-hidden />}
                >
                  Add
                </CfgButton>
              }
            />
          ))}
        </SectionCard>
      )}
      {defaultModel && (
        <p className="mt-1 text-[11px] text-[var(--cos-faint)]">
          Default chat model: <span className="font-mono text-[var(--cos-muted)]">{defaultModel}</span>
        </p>
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

function CollapsibleSection({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: ReactNode;
  count: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <section className="mb-3 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      >
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--cos-text)]">
          <ChevronRight size={14} aria-hidden className={`transition-transform ${open ? 'rotate-90' : ''}`} />
          {title}
          <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-normal text-[var(--cos-muted)]">
            {count}
          </span>
        </h3>
      </button>
      {open && (
        <div className="divide-y divide-[var(--cos-border)] border-t border-[var(--cos-border)]">{children}</div>
      )}
    </section>
  );
}

const HOOK_CATEGORY_ORDER = ['safety', 'enforcement', 'task', 'observability', 'reminder', 'other'];

function HooksTab() {
  const { data, isLoading, error } = useApiGet<{ hooks: HookRow[] }>(['config-hooks'], '/api/hooks/list');
  if (isLoading) return <StateRow>Loading hooks…</StateRow>;
  if (error) return <StateRow>Could not load hooks: {error.message}</StateRow>;
  const rows = data?.hooks ?? [];
  const byCategory = new Map<string, HookRow[]>();
  for (const h of rows) {
    const cat = h.category || 'other';
    const bucket = byCategory.get(cat) ?? [];
    bucket.push(h);
    byCategory.set(cat, bucket);
  }
  const categories = [...byCategory.keys()].sort((a, b) => {
    const rank = (c: string) => {
      const i = HOOK_CATEGORY_ORDER.indexOf(c);
      return i < 0 ? HOOK_CATEGORY_ORDER.length : i;
    };
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  return (
    <>
      <TabIntro>
        The hooks that steer the agent inside its guardrails — {rows.length} registered, grouped by role.
        These are DNA: read-only here (safety hooks can never be disabled).
      </TabIntro>
      {categories.map((cat) => (
        <CollapsibleSection
          key={cat}
          title={<span className="capitalize">{cat}</span>}
          count={byCategory.get(cat)!.length}
          defaultOpen={cat === 'safety'}
        >
          {byCategory.get(cat)!.map((h, i) => (
            <ConfigRow
              key={`${h.name}-${h.event ?? ''}-${i}`}
              title={h.name}
              badges={h.event ? <Pill tone="muted">{h.event}</Pill> : undefined}
              meta={
                <>
                  {h.matcher && (
                    <>
                      matcher <span className="font-mono">{h.matcher}</span>
                      {' · '}
                    </>
                  )}
                  phase {h.phase ?? '—'}
                </>
              }
            />
          ))}
        </CollapsibleSection>
      ))}
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
      const [resp] = await apiPatch<{ regenerated?: string[] }>(
        `/api/settings/modules/${encodeURIComponent(row.id)}`,
        { enabled: !row.enabled },
      );
      setNotes(resp?.regenerated ?? []);
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
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--cos-accent)]/40 bg-[var(--cos-accent)]/10 px-2.5 py-0.5 text-[10px] font-medium text-[var(--cos-accent)]">
                    <Lock size={11} aria-hidden />
                    kernel · locked
                  </span>
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

// META_REPO_SLUG is declared at the top of the file — coding-os ships trunk by
// default (ADR-0013); the Git tab stays fully editable but shows one caution on
// this slug (enabling pr-mode would flip the mother repo off trunk).

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
