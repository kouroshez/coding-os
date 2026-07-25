import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';
import { useScopedLink } from '@/lib/use-scoped-link';
import { Chip, FieldLabel, InfoTip, META_REPO_SLUG, StateRow, TabIntro } from './shared';
import {
  AUTONOMY_OPTIONS,
  FIELD_TIPS,
  INTEGRATION_BRANCH_CHIPS,
  inputClass,
  isBranchPattern,
} from './git-tab-data';
import type { AutonomyLevel, GitSettings, GitState } from './git-tab-data';
import { GitCapabilityStrip, GitQuickStart, ProtectedBranchesField } from './git-tab-fields';

export function GitTab() {
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

      <GitCapabilityStrip state={state} loading={stateLoading} error={stateError} />

      <GitQuickStart isActive={isPresetActive} onApply={applyPreset} />

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

        <ProtectedBranchesField
          selected={form.protected_branches}
          branches={branches}
          hasBranchList={hasBranchList}
          onChange={(next) => setForm({ ...form, protected_branches: next })}
        />

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
