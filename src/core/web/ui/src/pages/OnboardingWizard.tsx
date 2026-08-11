import { Modal } from '@/components/Modal';
import { ActionPill, Banner } from '@/layout/HubPrimitives';
import { CORE_SKILLS, INPUT_CLASS, PHASE_LABELS, PHASE_ORDER, readParkedJob } from './onboarding/wizard-constants';
import { Field, SkillRow, ToggleChip } from './onboarding/WizardControls';
import { useWizardComposer } from './onboarding/useWizardComposer';

// Re-exported for HubHome, which reads the parked job on mount.
export { readParkedJob };

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

export default function OnboardingWizard({
  suggestions, onClose, onCreated,
}: {
  suggestions: string[];
  onClose: () => void;
  onCreated: (slug: string) => void;
}) {
  const {
    adaptersData,
    advancedOpen,
    busy,
    canCreate,
    cancelJob,
    create,
    error,
    filteredPresets,
    isModuleOn,
    job,
    moduleCatalog,
    modulesData,
    nameOk,
    optionalSkills,
    presetQuery,
    presetsData,
    recommendedChips,
    requiredEntries,
    selectedStacks,
    setAdvancedOpen,
    setError,
    setJob,
    setPresetQuery,
    setState,
    slug,
    stacksByLanguage,
    state,
    toggle,
    toggleModule,
    validating,
    validation,
  } = useWizardComposer(suggestions, onClose, onCreated);
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
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-semibold text-[var(--cos-text)]">{p.label}</span>
                          {p.provenance === 'user' && (
                            <span
                              title="Authored by you (cos preset create) — not shipped with coding-os."
                              className="rounded bg-[var(--cos-bg)]/60 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--cos-faint)]"
                            >
                              yours
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-[var(--cos-muted)]">{p.description}</div>
                        <div className="mt-1.5 font-mono text-[10px] text-[var(--accent)]">{p.stacks.join(' + ')}</div>
                      </button>
                    </li>
                  ))}
                </ul>
                {state.preset === '' && (
                  <p className="text-[11px] leading-snug text-[var(--cos-muted)]">
                    Pick a preset to continue — or switch to “Compose my own” to select stacks
                    yourself (selecting none gives a base-only project).
                  </p>
                )}
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
                      Modules <span className="text-[var(--cos-faint)]">
                        (starts from the {modulesData?.default_profile ?? 'default'} profile — this is exactly what gets installed)
                      </span>
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
