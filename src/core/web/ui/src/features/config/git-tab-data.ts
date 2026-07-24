export type AutonomyLevel = 'local' | 'local_autonomous' | 'draft' | 'auto_merge' | 'autonomous';

export interface GitSettings {
  enabled: boolean;
  integration_branch: string;
  protected_branches: string[];
  autonomy_level: AutonomyLevel;
}

// Ordered low→high trust. `needsRemote` rungs push/PR and are unavailable when
// the probe reports no remote+gh; `local` always works (TASK-540).
export const AUTONOMY_OPTIONS: {
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

export interface GitState {
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
export const QUICK_START_PRESETS: {
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
export const FIELD_TIPS = {
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
export const INTEGRATION_BRANCH_CHIPS = ['main', 'develop', 'master'];
export const PROTECTED_BRANCH_CHIPS = ['production', 'main', 'release/*'];

export const inputClass =
  'mt-1 w-full rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-2.5 py-1.5 text-sm text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none';

export const isBranchPattern = (branch: string) =>
  branch.includes('*') || branch.includes('?') || branch.includes('[');
