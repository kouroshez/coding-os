import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { apiGet, apiPost } from '@/lib/api-client';
import { slugifyProjectName } from './HubHome';

/**
 * Full-screen onboarding wizard — TASK-358.
 *
 * PURPOSE: "New project" enters a step-wise flow instead of a single form:
 *          preset-or-custom → (custom: stacks) → agent → skills preview →
 *          extra skills → swimlanes preview → name-or-skip → description →
 *          review (validate-init dry-run) → create.
 * INPUT:   GET /api/hub/{presets,stacks,adapters,skills,stacks/{id}/skills};
 *          POST /api/hub/registry/{validate-init,init}.
 * OUTPUT:  A created+registered project; description seeds
 *          docs/_meta/project-description.md (TASK-364 intake).
 */

interface PresetItem { id: string; label: string; description: string; stacks: string[] }
interface StackItem { id: string; label: string; category: string; language: string }
interface AdapterItem { id: string; label: string }
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
  templates: string[]; swimlanes: string[]; conflicts: string[];
}

type StepId =
  | 'mode' | 'stacks' | 'agent' | 'skills' | 'extra'
  | 'swimlanes' | 'name' | 'description' | 'review';

const STEP_TITLES: Record<StepId, string> = {
  mode: 'How do you want to start?',
  stacks: 'Pick your stack(s)',
  agent: 'Which agent will work in this project?',
  skills: 'Skills this setup installs',
  extra: 'Add extra skills (optional)',
  swimlanes: 'Your board, composed',
  name: 'Name the project',
  description: 'Describe the project',
  review: 'Review & create',
};

export interface WizardState {
  mode: 'preset' | 'custom' | null;
  preset: string;
  stacks: string[];
  agent: string;
  extraSkills: string[];
  name: string;
  skipName: boolean;
  description: string;
  parentDir: string;
}

const INITIAL: WizardState = {
  mode: null, preset: '', stacks: [], agent: 'claude', extraSkills: [],
  name: '', skipName: false, description: '', parentDir: '',
};

export function wizardSteps(state: WizardState): StepId[] {
  return [
    'mode',
    ...(state.mode === 'custom' ? (['stacks'] as StepId[]) : []),
    'agent', 'skills', 'extra', 'swimlanes', 'name', 'description', 'review',
  ];
}

function Chip({
  active, label, hint, onClick, testId,
}: { active: boolean; label: string; hint?: string; onClick: () => void; testId?: string }) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      aria-pressed={active}
      title={hint}
      className={[
        'rounded border px-3 py-1.5 text-xs focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]',
        active
          ? 'border-[var(--cos-accent)] bg-[var(--cos-brand-tint)] text-[var(--cos-accent)]'
          : 'border-[var(--cos-border)] text-[var(--cos-muted)] hover:text-[var(--cos-text)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function SkillRow({ entry }: { entry: SkillEntry }) {
  return (
    <li className="flex items-baseline gap-2 text-xs">
      <code className="text-[var(--cos-text)]">{entry.name}</code>
      <span className="text-[10px] text-[var(--cos-faint)]">{entry.provenance}</span>
      {!entry.validated && (
        <span className="text-[10px] text-[var(--cos-warn,#eab308)]">not shipped yet</span>
      )}
    </li>
  );
}

export default function OnboardingWizard({
  suggestions, onClose, onCreated,
}: {
  suggestions: string[];
  onClose: () => void;
  onCreated: (slug: string) => void;
}) {
  const [state, setState] = useState<WizardState>({ ...INITIAL, parentDir: suggestions[0] ?? '' });
  const [stepIndex, setStepIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skillGroups, setSkillGroups] = useState<StackSkillGroups[]>([]);
  const [validation, setValidation] = useState<ValidatePayload | null>(null);

  const { data: presetsData } = useApiGet<{ presets: PresetItem[] }>(
    ['hub-presets'], '/api/hub/presets',
  );
  const { data: stacksData } = useApiGet<{ stacks: StackItem[] }>(['hub-stacks'], '/api/hub/stacks');
  const { data: adaptersData } = useApiGet<{ adapters: AdapterItem[] }>(
    ['hub-adapters'], '/api/hub/adapters',
  );
  const { data: catalogData } = useApiGet<{ skills: SkillEntry[] }>(['hub-skills'], '/api/hub/skills');

  const steps = wizardSteps(state);
  const step = steps[Math.min(stepIndex, steps.length - 1)];

  const selectedStacks = useMemo(() => {
    if (state.mode === 'preset') {
      return presetsData?.presets.find((p) => p.id === state.preset)?.stacks ?? [];
    }
    return state.stacks;
  }, [state.mode, state.preset, state.stacks, presetsData]);

  const stacksByLanguage = useMemo(() => {
    const groups = new Map<string, StackItem[]>();
    for (const s of stacksData?.stacks ?? []) {
      const lang = s.language || 'other';
      groups.set(lang, [...(groups.get(lang) ?? []), s]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [stacksData]);

  // Skills preview — fetched when the step is reached so back-nav keeps state.
  useEffect(() => {
    if (step !== 'skills' || selectedStacks.length === 0) return;
    let cancelled = false;
    void Promise.all(
      selectedStacks.map((id) =>
        apiGet<StackSkillGroups>(`/api/hub/stacks/${encodeURIComponent(id)}/skills`)
          .then(([data]) => data)
          .catch(() => null),
      ),
    ).then((results) => {
      if (!cancelled) setSkillGroups(results.filter(Boolean) as StackSkillGroups[]);
    });
    return () => { cancelled = true; };
  }, [step, selectedStacks]);

  const runValidate = useCallback(async (): Promise<ValidatePayload | null> => {
    setError(null);
    try {
      const [data] = await apiPost<ValidatePayload>('/api/hub/registry/validate-init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agent: state.agent,
      });
      setValidation(data);
      return data;
    } catch (err) {
      setValidation(null);
      setError(err instanceof Error ? err.message : 'validation failed');
      return null;
    }
  }, [state]);

  // Swimlane preview + review both run the dry-run validation on entry.
  useEffect(() => {
    if (step === 'swimlanes' || step === 'review') void runValidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const canContinue = useMemo(() => {
    switch (step) {
      case 'mode':
        return state.mode === 'preset' ? state.preset !== '' : state.mode === 'custom';
      case 'stacks':
        return state.stacks.length > 0;
      case 'agent':
        return state.agent !== '';
      case 'name':
        return state.skipName || /^[a-z0-9][a-z0-9._-]{0,63}$/.test(slugifyProjectName(state.name));
      case 'review':
        return Boolean(validation?.valid) && state.parentDir.trim() !== '';
      default:
        return true;
    }
  }, [step, state, validation]);

  const create = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [created] = await apiPost<{ slug: string }>('/api/hub/registry/init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agent: state.agent,
        description: state.description,
        extra_skills: state.extraSkills,
      });
      onCreated(created.slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'create failed');
    } finally {
      setBusy(false);
    }
  }, [state, onCreated]);

  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  const optionalSkills = useMemo(() => {
    const installed = new Set(
      skillGroups.flatMap((g) => [...g.groups.required, ...g.groups.recommended]).map((e) => e.name),
    );
    return (catalogData?.skills ?? []).filter(
      (s) => s.provenance === 'core' && !installed.has(s.name),
    );
  }, [catalogData, skillGroups]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Create a new project"
      className="fixed inset-0 z-50 flex flex-col bg-[var(--cos-bg)]"
    >
      {/* Header */}
      <header className="flex items-center justify-between border-b border-[var(--cos-border)] px-6 py-4">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">
            New project · step {steps.indexOf(step) + 1} / {steps.length}
          </div>
          <h1 className="text-sm font-semibold text-[var(--cos-text)]">{STEP_TITLES[step]}</h1>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close wizard"
          className="rounded px-2 py-1 text-sm text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        >
          ×
        </button>
      </header>

      {/* Body */}
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-2xl">
          {step === 'mode' && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <Chip
                  testId="mode-preset"
                  active={state.mode === 'preset'}
                  label="Start from a preset"
                  onClick={() => setState((s) => ({ ...s, mode: 'preset', stacks: [] }))}
                />
                <Chip
                  testId="mode-custom"
                  active={state.mode === 'custom'}
                  label="Compose my own"
                  onClick={() => setState((s) => ({ ...s, mode: 'custom', preset: '' }))}
                />
              </div>
              {state.mode === 'preset' && (
                <ul className="space-y-2">
                  {(presetsData?.presets ?? []).map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        aria-pressed={state.preset === p.id}
                        onClick={() => setState((s) => ({ ...s, preset: p.id }))}
                        className={[
                          'w-full rounded border p-3 text-left focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]',
                          state.preset === p.id
                            ? 'border-[var(--cos-accent)] bg-[var(--cos-brand-tint)]'
                            : 'border-[var(--cos-border)] hover:border-[var(--cos-accent)]',
                        ].join(' ')}
                      >
                        <div className="text-xs font-semibold text-[var(--cos-text)]">{p.label}</div>
                        <div className="text-[11px] text-[var(--cos-muted)]">{p.description}</div>
                        <div className="mt-1 font-mono text-[10px] text-[var(--cos-faint)]">
                          {p.stacks.join(' + ')}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {step === 'stacks' && (
            <div className="space-y-4">
              {stacksByLanguage.map(([language, stacks]) => (
                <div key={language}>
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">
                    {language}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {stacks.map((s) => (
                      <Chip
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
                Two stacks sharing a root (e.g. two backends) coexist under{' '}
                <code>src/services/&lt;stack&gt;/</code> automatically.
              </p>
            </div>
          )}

          {step === 'agent' && (
            <div className="flex flex-wrap gap-2">
              {(adaptersData?.adapters ?? []).map((a) => (
                <Chip
                  key={a.id}
                  active={state.agent === a.id}
                  label={a.label}
                  onClick={() => setState((s) => ({ ...s, agent: a.id }))}
                />
              ))}
            </div>
          )}

          {step === 'skills' && (
            <div className="space-y-4">
              {skillGroups.length === 0 && (
                <p className="text-xs text-[var(--cos-muted)]">
                  {selectedStacks.length === 0
                    ? 'Base install only — universal skills ship with every project.'
                    : 'Loading skill preview…'}
                </p>
              )}
              {skillGroups.map((g) => (
                <section key={g.stack}>
                  <h2 className="mb-1 text-xs font-semibold text-[var(--cos-text)]">{g.stack}</h2>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <div className="text-[10px] uppercase text-[var(--cos-muted)]">required</div>
                      <ul>{g.groups.required.map((e) => <SkillRow key={e.name} entry={e} />)}</ul>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase text-[var(--cos-muted)]">recommended</div>
                      <ul>{g.groups.recommended.map((e) => <SkillRow key={e.name} entry={e} />)}</ul>
                    </div>
                  </div>
                </section>
              ))}
            </div>
          )}

          {step === 'extra' && (
            <div className="space-y-2">
              <p className="text-[11px] text-[var(--cos-muted)]">
                Optional core skills beyond what your stacks install — manage later in Config.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {optionalSkills.map((s) => (
                  <Chip
                    key={s.name}
                    active={state.extraSkills.includes(s.name)}
                    label={s.name}
                    hint={s.description}
                    onClick={() =>
                      setState((st) => ({ ...st, extraSkills: toggle(st.extraSkills, s.name) }))}
                  />
                ))}
              </div>
            </div>
          )}

          {step === 'swimlanes' && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {(validation?.swimlanes ?? []).map((lane) => (
                  <span
                    key={lane}
                    className="rounded border border-[var(--cos-border)] px-2.5 py-1 text-[11px] text-[var(--cos-text)]"
                  >
                    {lane}
                  </span>
                ))}
              </div>
              {(validation?.conflicts?.length ?? 0) > 0 && (
                <div className="rounded border border-[var(--cos-border)] p-2 text-[10px] text-[var(--cos-muted)]">
                  <div className="mb-1 font-semibold">merge notes (later stack wins):</div>
                  {validation!.conflicts.map((c) => <div key={c} className="font-mono">{c}</div>)}
                </div>
              )}
            </div>
          )}

          {step === 'name' && (
            <div className="space-y-3">
              <label className="block text-xs">
                <span className="mb-1 block text-[var(--cos-muted)]">Project name</span>
                <input
                  type="text"
                  value={state.name}
                  disabled={state.skipName}
                  onChange={(e) => setState((s) => ({ ...s, name: e.target.value }))}
                  placeholder="my-app"
                  dir="auto"
                  className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                />
              </label>
              {!state.skipName && state.name.trim() && (
                <p className="text-[10px] text-[var(--cos-faint)]">
                  folder + slug: <code>{slugifyProjectName(state.name) || '—'}</code>
                </p>
              )}
              <Chip
                testId="skip-name"
                active={state.skipName}
                label="Don't know yet — pick a temp name for me"
                onClick={() => setState((s) => ({ ...s, skipName: !s.skipName }))}
              />
              <label className="block text-xs">
                <span className="mb-1 block text-[var(--cos-muted)]">Parent folder</span>
                <input
                  type="text"
                  value={state.parentDir}
                  onChange={(e) => setState((s) => ({ ...s, parentDir: e.target.value }))}
                  placeholder="/Users/you/code"
                  className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                />
              </label>
              {suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1 text-[10px]">
                  {suggestions.map((s) => (
                    <Chip
                      key={s}
                      active={state.parentDir === s}
                      label={s}
                      onClick={() => setState((st) => ({ ...st, parentDir: s }))}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {step === 'description' && (
            <label className="block text-xs">
              <span className="mb-1 block text-[var(--cos-muted)]">
                1–2 paragraphs: what is this project, for whom, what matters most?
                The agent screens this into your initial docs.
              </span>
              <textarea
                value={state.description}
                onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                rows={6}
                dir="auto"
                className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
              />
            </label>
          )}

          {step === 'review' && (
            <dl className="space-y-2 text-xs">
              <div><dt className="inline text-[var(--cos-muted)]">setup: </dt>
                <dd className="inline font-mono">
                  {state.mode === 'preset' ? `preset ${state.preset}` : selectedStacks.join(' + ') || 'base only'}
                </dd></div>
              <div><dt className="inline text-[var(--cos-muted)]">agent: </dt>
                <dd className="inline font-mono">{state.agent}</dd></div>
              <div><dt className="inline text-[var(--cos-muted)]">name: </dt>
                <dd className="inline font-mono">
                  {validation?.auto_named ? `${validation.name} (temp — rename later)` : validation?.name ?? '—'}
                </dd></div>
              <div><dt className="inline text-[var(--cos-muted)]">target: </dt>
                <dd className="inline font-mono">{validation?.target ?? '—'}</dd></div>
              <div><dt className="inline text-[var(--cos-muted)]">extra skills: </dt>
                <dd className="inline font-mono">{state.extraSkills.join(', ') || '—'}</dd></div>
              {!validation && !error && (
                <p className="text-[var(--cos-muted)]">validating…</p>
              )}
            </dl>
          )}

          {error && (
            <p role="alert" className="mt-4 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-400">
              {error}
            </p>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="flex items-center justify-between border-t border-[var(--cos-border)] px-6 py-4">
        <button
          type="button"
          onClick={() => (stepIndex === 0 ? onClose() : setStepIndex((i) => i - 1))}
          disabled={busy}
          className="rounded border border-[var(--cos-border)] px-3 py-1.5 text-xs text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        >
          {stepIndex === 0 ? 'Cancel' : 'Back'}
        </button>
        {step !== 'review' ? (
          <button
            type="button"
            data-testid="wizard-next"
            onClick={() => setStepIndex((i) => i + 1)}
            disabled={!canContinue || busy}
            className="rounded bg-[var(--cos-accent)] px-4 py-1.5 text-xs font-semibold text-[var(--cos-bg)] disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            Continue
          </button>
        ) : (
          <button
            type="button"
            data-testid="wizard-create"
            onClick={() => void create()}
            disabled={!canContinue || busy}
            className="rounded bg-[var(--cos-accent)] px-4 py-1.5 text-xs font-semibold text-[var(--cos-bg)] disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            {busy ? 'creating…' : 'Create project'}
          </button>
        )}
      </footer>
    </div>
  );
}
