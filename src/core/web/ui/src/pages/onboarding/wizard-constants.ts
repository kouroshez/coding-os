// Parked-job handoff (localStorage) + composer vocabulary.

export const PARKED_JOB_KEY = 'cos.init-job';
export const rememberJob = (id: string) => {
  try { window.sessionStorage.setItem(PARKED_JOB_KEY, id); } catch { /* private mode */ }
};
export const readParkedJob = (): string => {
  try { return window.sessionStorage.getItem(PARKED_JOB_KEY) ?? ''; } catch { return ''; }
};
export const forgetJob = () => {
  try { window.sessionStorage.removeItem(PARKED_JOB_KEY); } catch { /* private mode */ }
};


export const PHASE_ORDER = ['validate', 'scaffold', 'adapters', 'docs-seed', 'register', 'done'];
export const PHASE_LABELS: Record<string, string> = {
  validate: 'Validating your choices',
  scaffold: 'Scaffolding the project tree',
  adapters: 'Installing agent adapters',
  'docs-seed': 'Agent is processing your description & docs',
  register: 'Registering with the hub',
  done: 'Done',
};

export const NAME_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/;

// The 9 universal skills every project gets (base.yaml). Shown read-only so the
// user understands the floor without us pretending they are choices.
export const CORE_SKILLS = [
  'thinking_os', 'clean-code', 'graph-explorer', 'search', 'task-driver',
  'codebase-explorer', 'testing-strategy', 'observability', 'incident-response',
];


export const INPUT_CLASS =
  'w-full rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)] px-3 py-2 text-sm text-[var(--cos-text)] '
  + 'placeholder-[var(--cos-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]';

// --------------------------------------------------------------------------
// Composer
// --------------------------------------------------------------------------

