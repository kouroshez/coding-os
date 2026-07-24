import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { apiGet, apiPost } from '@/lib/api-client';
import { Modal } from '@/components/Modal';
import { ActionPill, Banner } from '@/layout/HubPrimitives';
import { slugifyProjectName } from './HubHome';

/**
 * New-project Composer — TASK-419 (supersedes the 8-step wizard, TASK-358).
 *
 * PURPOSE: One screen. Left = choices (template, name/folder/description,
 *          Advanced: agents + skills). Right = a live "what you'll get"
 *          preview driven by the validate-init dry-run. The fast path
 *          (pick a preset → Create) is ~3 interactions; depth is gated
 *          behind Advanced (progressive disclosure).
 * INPUT:   GET /api/hub/{presets,stacks,adapters,skills,stacks/{id}/skills};
 *          POST /api/hub/registry/{validate-init,init}.
 * OUTPUT:  A created+registered project; the description seeds
 *          docs/_meta/project-description.md → PRD (TASK-364). A project may
 *          host several adapters (agents is a list — hub.py::_resolve_agents).
 */

interface PresetItem { id: string; label: string; description: string; stacks: string[] }
interface StackItem { id: string; label: string; category: string; language: string }
interface AdapterItem { id: string; label: string }
interface ModuleItem { id: string; label: string; kernel: boolean; depends_on: string[] }
interface SkillEntry {
  name: string; tier: string | null; domain: string[];
  description: string; provenance: string; validated: boolean;
}
interface StackSkillGroups {
  stack: string;
  groups: { required: SkillEntry[]; recommended: SkillEntry[]; optional: SkillEntry[] };
}
interface ValidatePayload {
  valid: boolean; name: string; auto_named: boolean; target: string;
  templates: string[]; agents: string[]; swimlanes: string[]; conflicts: string[];
}

interface JobProgress {
  jobId: string;
  phase: string;
  log: string[];
  status: 'running' | 'succeeded' | 'failed' | 'cancelled';
  error: string;
}

const PHASE_ORDER = ['validate', 'scaffold', 'adapters', 'docs-seed', 'register', 'done'];
const PHASE_LABELS: Record<string, string> = {
  validate: 'Validating your choices',
  scaffold: 'Scaffolding the project tree',
  adapters: 'Installing agent adapters',
  'docs-seed': 'Agent is processing your description & docs',
  register: 'Registering with the hub',
  done: 'Done',
};

const NAME_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/;

// The 9 universal skills every project gets (base.yaml). Shown read-only so the
// user understands the floor without us pretending they are choices.
const CORE_SKILLS = [
  'thinking_os', 'clean-code', 'graph-explorer', 'search', 'task-driver',
  'codebase-explorer', 'testing-strategy', 'observability', 'incident-response',
];

interface ComposerState {
  mode: 'preset' | 'custom';
  preset: string;
  stacks: string[];
  agents: string[];
  extraSkills: string[];
  disabledModules: string[];
  name: string;
  skipName: boolean;
  description: string;
  parentDir: string;
}

// --------------------------------------------------------------------------
// Presentational primitives (tokens + ActionPill vocabulary, no raw hex)
// --------------------------------------------------------------------------

function ToggleChip({
  active, label, hint, locked, onClick, testId,
}: {
  active: boolean; label: string; hint?: string; locked?: boolean;
  onClick?: () => void; testId?: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={locked}
      aria-pressed={active}
      title={hint}
      className={[
        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
        locked
          ? 'cursor-default border-[var(--cos-border)] bg-[var(--cos-bg)]/40 text-[var(--cos-muted)]'
          : active
            ? 'border-[var(--accent)] bg-[var(--accent)]/12 text-[var(--accent)] shadow-sm'
            : 'border-[var(--cos-border)] bg-[var(--cos-panel)]/60 text-[var(--cos-text)] hover:border-[var(--accent)]/60 hover:text-[var(--accent)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function tierBadge(tier: string | null) {
  if (!tier) return null;
  return (
    <span className="rounded bg-[var(--cos-bg)]/60 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--cos-faint)]">
      {tier}
    </span>
  );
}

function SkillRow({ entry, action }: { entry: SkillEntry; action?: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 rounded-lg border border-[var(--cos-border)]/70 bg-[var(--cos-bg)]/30 px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <code className="text-xs font-semibold text-[var(--cos-text)]">{entry.name}</code>
          {tierBadge(entry.tier)}
          {entry.domain.slice(0, 3).map((d) => (
            <span key={d} className="rounded bg-[var(--accent)]/10 px-1.5 py-px text-[9px] text-[var(--accent)]">
              {d}
            </span>
          ))}
        </div>
        {entry.description && (
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-[var(--cos-muted)]">
            {entry.description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </li>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[var(--cos-text)]">{label}</span>
      {hint && <span className="mb-1.5 block text-[11px] leading-snug text-[var(--cos-muted)]">{hint}</span>}
      {children}
    </label>
  );
}

const INPUT_CLASS =
  'w-full rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)] px-3 py-2 text-sm text-[var(--cos-text)] '
  + 'placeholder-[var(--cos-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]';

// --------------------------------------------------------------------------
// Composer
// --------------------------------------------------------------------------

export default function OnboardingWizard({
  suggestions, onClose, onCreated,
}: {
  suggestions: string[];
  onClose: () => void;
  onCreated: (slug: string) => void;
}) {
  const [state, setState] = useState<ComposerState>({
    mode: 'preset', preset: '', stacks: [], agents: ['claude'],
    extraSkills: [], disabledModules: [], name: '', skipName: false, description: '',
    parentDir: suggestions[0] ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [skillGroups, setSkillGroups] = useState<StackSkillGroups[]>([]);
  const [validation, setValidation] = useState<ValidatePayload | null>(null);
  const [validating, setValidating] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [presetQuery, setPresetQuery] = useState('');
  const [job, setJob] = useState<JobProgress | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: presetsData } = useApiGet<{ presets: PresetItem[] }>(['hub-presets'], '/api/hub/presets');
  const { data: stacksData } = useApiGet<{ stacks: StackItem[] }>(['hub-stacks'], '/api/hub/stacks');
  const { data: adaptersData } = useApiGet<{ adapters: AdapterItem[] }>(['hub-adapters'], '/api/hub/adapters');
  const { data: catalogData } = useApiGet<{ skills: SkillEntry[] }>(['hub-skills'], '/api/hub/skills');
  const { data: modulesData } = useApiGet<{ modules: ModuleItem[] }>(['hub-modules'], '/api/hub/modules');

  const selectedStacks = useMemo(() => {
    if (state.mode === 'preset') {
      return presetsData?.presets.find((p) => p.id === state.preset)?.stacks ?? [];
    }
    return state.stacks;
  }, [state.mode, state.preset, state.stacks, presetsData]);
  const stacksSig = selectedStacks.join(',');

  const stacksByLanguage = useMemo(() => {
    const groups = new Map<string, StackItem[]>();
    for (const s of stacksData?.stacks ?? []) {
      const lang = s.language || 'other';
      groups.set(lang, [...(groups.get(lang) ?? []), s]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [stacksData]);

  const filteredPresets = useMemo(() => {
    const q = presetQuery.trim().toLowerCase();
    const all = presetsData?.presets ?? [];
    if (!q) return all;
    return all.filter(
      (p) => p.label.toLowerCase().includes(q)
        || p.description.toLowerCase().includes(q)
        || p.stacks.some((s) => s.toLowerCase().includes(q)),
    );
  }, [presetsData, presetQuery]);

  // Skill groups for the selected stacks + auto-seed recommended core skills
  // into extra_skills (they are NOT auto-installed by the scaffold — only the
  // stack's own skill dirs are linked, so the curated core companions need to
  // ride the --skills flag). Re-seeds whenever the stack set changes; user
  // toggles persist within a stack set.
  useEffect(() => {
    if (selectedStacks.length === 0) { setSkillGroups([]); setState((s) => ({ ...s, extraSkills: [] })); return; }
    let cancelled = false;
    void Promise.all(
      selectedStacks.map((id) =>
        apiGet<StackSkillGroups>(`/api/hub/stacks/${encodeURIComponent(id)}/skills`)
          .then(([data]) => data)
          .catch(() => null)),
    ).then((results) => {
      if (cancelled) return;
      const groups = results.filter(Boolean) as StackSkillGroups[];
      setSkillGroups(groups);
      const seed = new Set<string>();
      for (const g of groups) {
        for (const e of g.groups.recommended) {
          if (e.provenance === 'core' && e.validated) seed.add(e.name);
        }
      }
      setState((s) => ({ ...s, extraSkills: [...seed] }));
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stacksSig]);

  const runValidate = useCallback(async () => {
    if (!state.parentDir.trim()) { setValidation(null); return; }
    setValidating(true);
    setError(null);
    try {
      const [data] = await apiPost<ValidatePayload>('/api/hub/registry/validate-init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agents: state.agents,
        disabled_modules: state.disabledModules,
      });
      setValidation(data);
    } catch (err) {
      setValidation(null);
      setError(err instanceof Error ? err.message : 'validation failed');
    } finally {
      setValidating(false);
    }
  }, [state.parentDir, state.skipName, state.name, state.mode, state.stacks, state.preset, state.agents, state.disabledModules]);

  // Debounced live preview — re-validates whenever a relevant choice changes.
  useEffect(() => {
    const t = setTimeout(() => { void runValidate(); }, 350);
    return () => clearTimeout(t);
  }, [runValidate]);

  const recommendedChips = useMemo(() => {
    const seen = new Set<string>();
    const out: SkillEntry[] = [];
    for (const g of skillGroups) {
      for (const e of g.groups.recommended) {
        if (e.provenance === 'core' && e.validated && !seen.has(e.name)) { seen.add(e.name); out.push(e); }
      }
    }
    return out;
  }, [skillGroups]);

  const requiredEntries = useMemo(() => {
    const seen = new Set<string>();
    const out: SkillEntry[] = [];
    for (const g of skillGroups) {
      for (const e of g.groups.required) {
        if (!seen.has(e.name)) { seen.add(e.name); out.push(e); }
      }
    }
    return out;
  }, [skillGroups]);

  const optionalSkills = useMemo(() => {
    const installed = new Set(
      skillGroups.flatMap((g) => [...g.groups.required, ...g.groups.recommended]).map((e) => e.name),
    );
    return (catalogData?.skills ?? []).filter(
      (s) => s.provenance === 'core' && s.validated && !installed.has(s.name) && !CORE_SKILLS.includes(s.name),
    );
  }, [catalogData, skillGroups]);

  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  const moduleCatalog = modulesData?.modules ?? [];
  const isModuleOn = (id: string) => !state.disabledModules.includes(id);
  // Toggle a module, keeping the dependency graph valid (tasks needs docs):
  // disabling a module also disables its dependents; enabling re-enables deps.
  const toggleModule = (id: string) => setState((s) => {
    const disabled = new Set(s.disabledModules);
    if (disabled.has(id)) {
      disabled.delete(id);
      for (const dep of moduleCatalog.find((m) => m.id === id)?.depends_on ?? []) disabled.delete(dep);
    } else {
      disabled.add(id);
      for (const m of moduleCatalog) if (m.depends_on.includes(id)) disabled.add(m.id);
    }
    return { ...s, disabledModules: [...disabled] };
  });

  const slug = slugifyProjectName(state.name);
  // Empty name is fine — the backend assigns a temp slug (auto_named). Only a
  // non-empty name has to be a valid slug.
  const nameOk = state.skipName || slug === '' || NAME_RE.test(slug);
  const choiceOk = state.mode === 'preset' ? state.preset !== '' : true;
  const canCreate = Boolean(validation?.valid) && state.parentDir.trim() !== ''
    && nameOk && choiceOk && state.agents.length > 0 && !busy;

  const create = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [started] = await apiPost<{ job_id: string; name: string }>('/api/hub/registry/init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agents: state.agents,
        description: state.description,
        extra_skills: state.extraSkills,
        disabled_modules: state.disabledModules,
        background: true,
      });
      setJob({ jobId: started.job_id, phase: 'validate', log: [], status: 'running', error: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'create failed');
      setBusy(false);
    }
  }, [state]);

  // Job progress stream (TASK-362): replay + follow; reconnects after refresh.
  useEffect(() => {
    if (!job || job.status !== 'running') return;
    const source = new EventSource(`/api/hub/init-jobs/${encodeURIComponent(job.jobId)}/events`);
    const append = (line: string) =>
      setJob((j) => (j ? { ...j, log: [...j.log.slice(-199), line] } : j));
    source.addEventListener('log', (e) => append((JSON.parse((e as MessageEvent).data) as { line: string }).line));
    source.addEventListener('phase', (e) =>
      setJob((j) => (j ? { ...j, phase: (JSON.parse((e as MessageEvent).data) as { phase: string }).phase } : j)));
    const terminal = (status: JobProgress['status']) => (e: Event) => {
      const payload = JSON.parse((e as MessageEvent).data) as { error?: string; result?: { slug?: string } };
      source.close();
      setBusy(false);
      if (status === 'succeeded') { onCreated(payload.result?.slug ?? ''); return; }
      setJob((j) => (j ? { ...j, status, error: payload.error ?? '' } : j));
      if (status === 'failed') setError(payload.error || 'init failed');
    };
    source.addEventListener('succeeded', terminal('succeeded'));
    source.addEventListener('failed', terminal('failed'));
    source.addEventListener('cancelled', terminal('cancelled'));
    source.onerror = () => { /* EventSource auto-reconnects; job state is server-side */ };
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.jobId, job?.status]);

  const cancelJob = useCallback(async () => {
    if (!job) return;
    try {
      await apiPost(`/api/hub/init-jobs/${encodeURIComponent(job.jobId)}/cancel`, {});
    } catch {
      // terminal event (or 404) resolves the UI state either way
    }
  }, [job]);

  // ---- Job progress view -------------------------------------------------
  if (job) {
    const running = job.status === 'running';
    return (
      <Modal
        open
        onClose={running ? () => {} : onClose}
        title={running ? 'Creating your project…' : `Create ${job.status}`}
        size="lg"
        footer={running ? (
          <ActionPill label="Cancel" onClick={() => void cancelJob()} />
        ) : (
          <ActionPill label="Back to composer" onClick={() => { setJob(null); setError(null); }} />
        )}
      >
        <ol className="space-y-1.5" data-testid="job-phases">
          {PHASE_ORDER.map((p) => {
            const reached = PHASE_ORDER.indexOf(p) <= PHASE_ORDER.indexOf(job.phase);
            const current = p === job.phase && running;
            return (
              <li
                key={p}
                aria-current={current ? 'step' : undefined}
                className={['flex items-center gap-2 text-sm', reached ? 'text-[var(--cos-text)]' : 'text-[var(--cos-faint)]'].join(' ')}
              >
                <span aria-hidden="true">{reached ? (current ? '◌' : '●') : '○'}</span>
                {PHASE_LABELS[p] ?? p}
              </li>
            );
          })}
        </ol>
        <pre
          data-testid="job-log"
          className="mt-4 max-h-64 overflow-y-auto rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)]/40 p-3 font-mono text-[10px] text-[var(--cos-muted)]"
        >
          {job.log.join('\n') || '…'}
        </pre>
        {job.status === 'cancelled' && (
          <p className="mt-3 text-xs text-[var(--cos-muted)]">
            Cancelled — the partial scaffold was removed. Nothing was created.
          </p>
        )}
        {error && <div role="alert" className="mt-3"><Banner kind="error">{error}</Banner></div>}
      </Modal>
    );
  }

  // ---- Composer view -----------------------------------------------------
  const setupSummary = state.mode === 'preset'
    ? (presetsData?.presets.find((p) => p.id === state.preset)?.label ?? '—')
    : (selectedStacks.join(' + ') || 'base only');

  return (
    <Modal
      open
      onClose={onClose}
      title="Create a new project"
      size="xl"
      footer={(
        <>
          <ActionPill label="Cancel" onClick={onClose} />
          <ActionPill
            label={busy ? 'Creating…' : 'Create project'}
            onClick={() => void create()}
            disabled={!canCreate}
            primary
          />
        </>
      )}
    >
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        {/* ---- Left: choices ---- */}
        <div className="space-y-6">
          {/* Template */}
          <section>
            <div className="mb-2 inline-flex rounded-lg border border-[var(--cos-border)] p-0.5">
              {(['preset', 'custom'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  data-testid={`mode-${m}`}
                  onClick={() => setState((s) => ({ ...s, mode: m }))}
                  className={[
                    'rounded-md px-3 py-1 text-xs font-medium transition-colors',
                    state.mode === m ? 'bg-[var(--accent)] text-[var(--cos-bg)]' : 'text-[var(--cos-muted)] hover:text-[var(--cos-text)]',
                  ].join(' ')}
                >
                  {m === 'preset' ? 'Start from a preset' : 'Compose my own'}
                </button>
              ))}
            </div>

            {state.mode === 'preset' ? (
              <div className="space-y-2">
                <input
                  type="text"
                  value={presetQuery}
                  onChange={(e) => setPresetQuery(e.target.value)}
                  placeholder="Filter presets…"
                  aria-label="Filter presets"
                  className={INPUT_CLASS}
                />
                <ul className="grid max-h-[320px] gap-2 overflow-y-auto cos-scroll pr-1 sm:grid-cols-2">
                  {filteredPresets.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        aria-pressed={state.preset === p.id}
                        onClick={() => setState((s) => ({ ...s, preset: p.id }))}
                        className={[
                          'h-full w-full rounded-xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
                          state.preset === p.id
                            ? 'border-[var(--accent)] bg-[var(--accent)]/8 shadow-sm'
                            : 'border-[var(--cos-border)] bg-[var(--cos-panel)]/50 hover:border-[var(--accent)]/60',
                        ].join(' ')}
                      >
                        <div className="text-sm font-semibold text-[var(--cos-text)]">{p.label}</div>
                        <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-[var(--cos-muted)]">{p.description}</div>
                        <div className="mt-1.5 font-mono text-[10px] text-[var(--accent)]">{p.stacks.join(' + ')}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="space-y-3">
                {stacksByLanguage.map(([language, stacks]) => (
                  <div key={language}>
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">{language}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {stacks.map((s) => (
                        <ToggleChip
                          key={s.id}
                          active={state.stacks.includes(s.id)}
                          label={s.label}
                          hint={s.category}
                          onClick={() => setState((st) => ({ ...st, stacks: toggle(st.stacks, s.id) }))}
                        />
                      ))}
                    </div>
                  </div>
                ))}
                <p className="text-[11px] text-[var(--cos-muted)]">
                  Two stacks sharing a root coexist under <code>src/services/&lt;stack&gt;/</code> automatically.
                </p>
              </div>
            )}
          </section>

          {/* Identity */}
          <section className="space-y-3">
            <Field label="Project name" hint="Optional — leave blank for a temporary slug you can rename later.">
              <input
                type="text"
                value={state.name}
                disabled={state.skipName}
                onChange={(e) => setState((s) => ({ ...s, name: e.target.value }))}
                placeholder="my-app"
                dir="auto"
                className={INPUT_CLASS}
              />
            </Field>
            <div className="flex flex-wrap items-center gap-2">
              <ToggleChip
                testId="skip-name"
                active={state.skipName}
                label="Pick a temp name for me"
                onClick={() => setState((s) => ({ ...s, skipName: !s.skipName }))}
              />
              {!state.skipName && state.name.trim() && (
                <span className="text-[11px] text-[var(--cos-faint)]">slug: <code>{slug || '—'}</code></span>
              )}
              {!nameOk && <span className="text-[11px] text-[var(--cos-err)]">lowercase, no spaces</span>}
            </div>
            <Field label="Parent folder">
              <input
                type="text"
                value={state.parentDir}
                onChange={(e) => setState((s) => ({ ...s, parentDir: e.target.value }))}
                placeholder="/Users/you/code"
                className={`${INPUT_CLASS} font-mono`}
              />
            </Field>
            {suggestions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <ToggleChip
                    key={s}
                    active={state.parentDir === s}
                    label={s}
                    onClick={() => setState((st) => ({ ...st, parentDir: s }))}
                  />
                ))}
              </div>
            )}
            <Field
              label="What is this project?"
              hint="1–2 sentences: what it is, for whom, what matters most. The agent expands this into your starter docs (PRD)."
            >
              <textarea
                value={state.description}
                onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                rows={3}
                dir="auto"
                placeholder="A booking app for indie venues — fast checkout matters most."
                className={INPUT_CLASS}
              />
            </Field>
          </section>

          {/* Advanced */}
          <section>
            <button
              type="button"
              onClick={() => setAdvancedOpen((v) => !v)}
              aria-expanded={advancedOpen}
              className="flex w-full items-center justify-between rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-3 py-2 text-xs font-medium text-[var(--cos-text)] hover:border-[var(--accent)]/60"
            >
              <span>
                Advanced — agents &amp; skills
                {!advancedOpen && (
                  <span className="text-[var(--cos-faint)]">
                    {` · ${state.agents.length} agent${state.agents.length === 1 ? '' : 's'}`}
                    {state.extraSkills.length > 0 ? `, ${state.extraSkills.length} skill${state.extraSkills.length === 1 ? '' : 's'} on` : ''}
                  </span>
                )}
              </span>
              <span aria-hidden="true" className="text-[var(--cos-muted)]">{advancedOpen ? '▲' : '▼'}</span>
            </button>

            {advancedOpen && (
              <div className="mt-3 space-y-5">
                <div>
                  <div className="mb-1.5 text-xs font-medium text-[var(--cos-text)]">Agents</div>
                  <p className="mb-2 text-[11px] text-[var(--cos-muted)]">
                    A project can host more than one adapter (e.g. both Claude Code and Codex).
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(adaptersData?.adapters ?? []).map((a) => (
                      <ToggleChip
                        key={a.id}
                        testId={`agent-${a.id}`}
                        active={state.agents.includes(a.id)}
                        label={a.label}
                        onClick={() => setState((s) => ({
                          ...s,
                          // keep at least one agent selected
                          agents: s.agents.includes(a.id) && s.agents.length === 1
                            ? s.agents
                            : toggle(s.agents, a.id),
                        }))}
                      />
                    ))}
                  </div>
                </div>

                {recommendedChips.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-[var(--cos-text)]">
                      Recommended skills <span className="text-[var(--cos-faint)]">(on by default)</span>
                    </div>
                    <ul className="space-y-1.5">
                      {recommendedChips.map((e) => (
                        <SkillRow
                          key={e.name}
                          entry={e}
                          action={(
                            <ToggleChip
                              active={state.extraSkills.includes(e.name)}
                              label={state.extraSkills.includes(e.name) ? 'on' : 'off'}
                              onClick={() => setState((s) => ({ ...s, extraSkills: toggle(s.extraSkills, e.name) }))}
                            />
                          )}
                        />
                      ))}
                    </ul>
                  </div>
                )}

                {optionalSkills.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-[var(--cos-text)]">More skills</div>
                    <div className="flex flex-wrap gap-1.5">
                      {optionalSkills.map((s) => (
                        <ToggleChip
                          key={s.name}
                          active={state.extraSkills.includes(s.name)}
                          label={s.name}
                          hint={s.description}
                          onClick={() => setState((st) => ({ ...st, extraSkills: toggle(st.extraSkills, s.name) }))}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {moduleCatalog.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-[var(--cos-text)]">
                      Modules <span className="text-[var(--cos-faint)]">(on by default — turn off what you don&apos;t need)</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {moduleCatalog.map((m) => (
                        <ToggleChip
                          key={m.id}
                          testId={`module-${m.id}`}
                          active={isModuleOn(m.id)}
                          locked={m.kernel}
                          label={m.label.split(' — ')[0]}
                          hint={m.kernel
                            ? 'Kernel — always on'
                            : (m.depends_on.length ? `needs: ${m.depends_on.join(', ')}` : m.label)}
                          onClick={m.kernel ? undefined : () => toggleModule(m.id)}
                        />
                      ))}
                    </div>
                    <p className="mt-1.5 text-[11px] leading-snug text-[var(--cos-muted)]">
                      Kernel is always on. Turning a module off also turns off anything that depends on it. Adjustable later in Config.
                    </p>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        {/* ---- Right: live preview ---- */}
        <aside>
          <div className="rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-bg)]/40 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--cos-muted)]">What you&apos;ll get</h3>
              {validating && <span className="text-[10px] text-[var(--cos-faint)]">updating…</span>}
            </div>

            <dl className="space-y-2.5 text-xs">
              <div>
                <dt className="text-[var(--cos-muted)]">Setup</dt>
                <dd className="font-medium text-[var(--cos-text)]">{setupSummary}</dd>
              </div>
              <div>
                <dt className="text-[var(--cos-muted)]">Agents</dt>
                <dd className="mt-1 flex flex-wrap gap-1">
                  {state.agents.map((a) => (
                    <span key={a} className="rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2 py-0.5 text-[11px] text-[var(--accent)]">{a}</span>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--cos-muted)]">Name → folder</dt>
                <dd className="font-mono text-[11px] text-[var(--cos-text)]">
                  {validation?.auto_named ? `${validation.name} (temp)` : (validation?.name || (state.skipName ? 'auto' : slug || '—'))}
                </dd>
              </div>
              {validation?.target && (
                <div>
                  <dt className="text-[var(--cos-muted)]">Location</dt>
                  <dd className="break-all font-mono text-[10px] text-[var(--cos-muted)]">{validation.target}</dd>
                </div>
              )}
              {(validation?.swimlanes?.length ?? 0) > 0 && (
                <div>
                  <dt className="text-[var(--cos-muted)]">Board lanes</dt>
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {validation!.swimlanes.map((lane) => (
                      <span key={lane} className="inline-flex items-center gap-1 rounded-md border border-[var(--cos-border)] px-1.5 py-0.5 text-[10px] text-[var(--cos-text)]">
                        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]/60" />{lane}
                      </span>
                    ))}
                  </dd>
                </div>
              )}
            </dl>

            {requiredEntries.length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">Skills your stack installs</div>
                <ul className="space-y-1.5">
                  {requiredEntries.map((e) => <SkillRow key={e.name} entry={e} />)}
                </ul>
              </div>
            )}

            <div className="mt-4 border-t border-[var(--cos-border)] pt-3">
              <div className="mb-1.5 text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">Core skills — always on</div>
              <div className="flex flex-wrap gap-1">
                {CORE_SKILLS.map((name) => (
                  <span
                    key={name}
                    title="The cognitive floor — installed on every project, cannot be removed."
                    className="inline-flex items-center gap-1 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] text-[var(--accent)]"
                  >
                    <span aria-hidden="true">✓</span>{name}
                  </span>
                ))}
              </div>
              <p className="mt-1.5 text-[10px] leading-snug text-[var(--cos-faint)]">
                The cognitive floor — memory, structure, discipline. Installed on every project.
              </p>
            </div>
          </div>
        </aside>
      </div>

      {error && <div role="alert" className="mt-4"><Banner kind="error">{error}</Banner></div>}
    </Modal>
  );
}
