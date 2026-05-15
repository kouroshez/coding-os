// Fixtures for cos board — coding-os Phase L dogfood data
const SWIMLANES = [
  { id: 'core',        label: 'core',        color: '#6b7280', accent: '#374151' },
  { id: 'thinking_os', label: 'thinking_os', color: '#8b5cf6', accent: '#6d28d9' },
  { id: 'graph_os',    label: 'graph_os',    color: '#0891b2', accent: '#0e7490' },
  { id: 'board_os',    label: 'board_os',    color: '#ea580c', accent: '#c2410c' },
  { id: 'adapters',    label: 'adapters',    color: '#16a34a', accent: '#15803d' },
  { id: 'templates',   label: 'templates',   color: '#db2777', accent: '#be185d' },
  { id: 'cli',         label: 'cli',         color: '#ca8a04', accent: '#a16207' },
  { id: 'docs',        label: 'docs',        color: '#4f46e5', accent: '#4338ca' },
];

const COLUMNS = [
  { id: 'icebox',      label: 'ICE BOX',     sub: 'backlog',            wip: null },
  { id: 'ready',       label: 'READY',       sub: 'up next',            wip: null },
  { id: 'emergency',   label: 'EMERGENCY',   sub: 'fire — skip queue',  wip: 2 },
  { id: 'in_progress', label: 'IN PROGRESS', sub: 'active work',        wip: 1 },
  { id: 'testing',     label: 'TESTING',     sub: 'verifying G/W/T',    wip: 3 },
  { id: 'blocked',     label: 'BLOCKED',     sub: 'external dep',       wip: null },
  { id: 'complete',    label: 'COMPLETE',    sub: 'acceptance met',     wip: null },
  { id: 'archive',     label: 'ARCHIVE',     sub: 'frozen',             wip: null },
];

const KIND_COLORS = {
  bug:      { bg: 'var(--sticky-red)',    bg2: 'var(--sticky-red-2)',    chip: '#b91c1c', label: 'bug' },
  feature:  { bg: 'var(--sticky-yellow)', bg2: 'var(--sticky-yellow-2)', chip: '#a16207', label: 'feat' },
  chore:    { bg: 'var(--sticky-green)',  bg2: 'var(--sticky-green-2)',  chip: '#15803d', label: 'chore' },
  spike:    { bg: 'var(--sticky-blue)',   bg2: 'var(--sticky-blue-2)',   chip: '#1d4ed8', label: 'spike' },
  docs:     { bg: 'var(--sticky-purple)', bg2: 'var(--sticky-purple-2)', chip: '#7e22ce', label: 'docs' },
  refactor: { bg: 'var(--sticky-teal)',   bg2: '#5eead4',                chip: '#0f766e', label: 'refactor' },
  test:     { bg: 'var(--sticky-orange)', bg2: 'var(--sticky-orange-2)', chip: '#c2410c', label: 'test' },
  security: { bg: '#ffd8a8',              bg2: '#fdba74',                chip: '#9a3412', label: 'sec' },
};

const EPICS = [
  { id: 'phase-l', label: 'phase-l-scrumban' },
  { id: 'phase-i', label: 'phase-i-graph' },
  { id: 'phase-k', label: 'phase-k-memory' },
  { id: 'infra-q2', label: 'infra-q2' },
  { id: 'dogfood', label: 'dogfood' },
];

// agents currently live
const AGENTS = [
  { id: 'claude',  session: 'ses-claude-20260419-7af3', color: '#d97706', glyph: 'C' },
  { id: 'codex',   session: 'ses-codex-20260419-99bb',  color: '#0891b2', glyph: 'X' },
  { id: 'human',   session: 'local-mac',                 color: '#16a34a', glyph: 'H' },
];

const T = (id, title, swimlane, kind, status, priority, appetite, epic, opts = {}) => ({
  id: `TASK-${String(id).padStart(3, '0')}`,
  title, swimlane, kind, status, priority, appetite, epic,
  labels: opts.labels || [],
  agent: opts.agent || null,
  started: opts.started || null,
  workLog: opts.workLog || [],
  blockedReason: opts.blockedReason || null,
  stale: opts.stale || false,
  rotation: opts.rotation ?? (Math.random() * 3 - 1.5),
  depends: opts.depends || [],
});

// rich fixture set
const TASKS = [
  // ========== ICE BOX ==========
  T(201, 'Parallel graph backends via plugin registry',    'graph_os',    'spike',    'icebox', 'P2', '3d',   'phase-i',  { labels: ['indexing'], rotation: -1.2 }),
  T(202, 'Kuzu vs DuckDB benchmark on 500k-symbol fixture','graph_os',    'spike',    'icebox', 'P2', '1d',   'phase-i',  { labels: ['perf', 'benchmark'], rotation: 0.8 }),
  T(203, 'Retire docs/tasks.md index file',                'docs',        'chore',    'icebox', 'P3', '2h',   'phase-l',  { rotation: 1.4 }),
  T(204, 'Template-drift CI test (R-L-24)',                'templates',   'test',     'icebox', 'P2', '4h',   'phase-l',  { rotation: -0.6 }),
  T(205, 'Rename hook ordering semantics doc',             'docs',        'docs',     'icebox', 'P3', '1h',   null,       { rotation: 0.2 }),
  T(206, 'Explore Basecamp-style 6-week cycles',           'core',        'spike',    'icebox', 'P3', '3d',   null,       { rotation: -1.8, labels: ['cycle', 'shape-up'] }),
  T(207, 'Deprecate legacy 4-status aliases (eventually)', 'board_os',    'chore',    'icebox', 'P3', '4h',   'phase-l',  { rotation: 0.9 }),

  // ========== READY ==========
  T(210, 'Migration v13: add status_history + columns',    'board_os',    'feature',  'ready',  'P0', '1d',   'phase-l',  { labels: ['migration', 'db'], rotation: -0.8, depends: [] }),
  T(211, 'scrumban-config.yaml schema + validator',        'board_os',    'feature',  'ready',  'P0', '1d',   'phase-l',  { rotation: 0.6 }),
  T(212, 'Lean task template (frontmatter + G/W/T + log)', 'templates',   'feature',  'ready',  'P0', '4h',   'phase-l',  { rotation: 1.1, labels: ['ssot'] }),
  T(213, 'Per-stack scrumban-config overrides',            'templates',   'feature',  'ready',  'P1', '6h',   'phase-l',  { rotation: -0.3 }),
  T(214, 'Sigma.js WebGL graph renderer',                  'graph_os',    'feature',  'ready',  'P1', '2d',   'phase-i',  { rotation: 0.7 }),

  // ========== EMERGENCY ==========
  T(220, 'Hook adapter crashes on Codex PostToolUse',      'adapters',    'bug',      'emergency', 'P0', '4h', 'dogfood',  { labels: ['codex', 'hooks'], rotation: 2.1, agent: 'claude',
      workLog: [
        '2026-04-19 [claude | 7af3]: reproduced on clean Codex session; stack trace in .coding-os/.hook-err.log',
        '2026-04-19 [claude | 7af3]: traced to missing session_id env var — Codex doesn\'t set CLAUDE_SESSION',
      ] }),
  T(221, 'Agent creates P0 archived — state machine hole', 'board_os',    'bug',      'emergency', 'P0', '2h', 'phase-l',  { labels: ['workflow'], rotation: -1.4, stale: true,
      workLog: [
        '2026-04-19 [codex | 99bb]: agent TRIED to transition icebox → complete directly; workflow.py allowed it',
        '2026-04-19 [codex | 99bb]: property-based test reproduces on 3/60 transitions',
      ] }),

  // ========== IN PROGRESS (wip cap = 1) ==========
  T(230, 'workflow.py state machine + WIP engine',         'board_os',    'feature',  'in_progress', 'P0', '1d', 'phase-l', {
      labels: ['state-machine'], rotation: -0.4, agent: 'claude', started: '2026-04-19',
      workLog: [
        '2026-04-19 [claude | 7af3]: transition() signature drafted; 14/60 tests green',
        '2026-04-19 [claude | 7af3]: WIP cap pre-check wired; flock() around frontmatter write',
        '2026-04-19 [claude | 7af3]: optimistic concurrency (R-L-29) prototype — reading current status pre-write works',
      ] }),

  // WIP violation: a second in_progress task (cap=1)
  T(231, 'Sortable.js drag-drop wiring (viewer)',          'board_os',    'feature',  'in_progress', 'P1', '6h', 'phase-l', {
      rotation: 1.3, agent: 'codex', started: '2026-04-19',
      workLog: [
        '2026-04-19 [codex | 99bb]: columns rendered; swimlane bands aligned',
        '2026-04-19 [codex | 99bb]: Sortable group="cards" across lanes; ghost preview landing OK',
      ] }),

  // ========== TESTING (wip cap = 3) ==========
  T(240, 'parser.py frontmatter round-trip (40 tests)',    'board_os',    'test',     'testing', 'P0', '4h', 'phase-l',   {
      rotation: -0.9, agent: 'claude',
      workLog: [
        '2026-04-18 [claude | 7af3]: 40/40 green on legacy fallback; Persian titles (R-L-22) parse clean',
        '2026-04-19 [claude | 7af3]: idempotence property test added',
      ] }),
  T(241, 'Dependency cycle detector (R-L-29)',             'board_os',    'feature',  'testing', 'P1', '3h', 'phase-l',   {
      rotation: 0.5, agent: 'claude',
      workLog: [
        '2026-04-19 [claude | 7af3]: DFS walk impl; A→B→C→A rejected with full path shown',
      ] }),
  T(242, 'Two-phase atomic migration (R-L-27)',            'board_os',    'refactor', 'testing', 'P1', '6h', 'phase-l',   {
      rotation: 1.6, agent: 'human',
      workLog: [
        '2026-04-17 [human | local-mac]: backup → validate-staging → atomic rename; rollback tarball works',
        '2026-04-19 [human | local-mac]: resumable --resume path covered on interrupted validate',
      ] }),

  // ========== BLOCKED ==========
  T(250, 'Kuzu HNSW index parity with SQLite vec', 'graph_os', 'feature', 'blocked', 'P1', '2d', 'phase-i', {
      rotation: -1.1, blockedReason: 'waiting on Kuzu 0.5 release for HNSW stability fix',
      workLog: [
        '2026-04-15 [claude | 3fa2]: 35/50 parity tests green; 15 flaky on HNSW recall',
        '2026-04-16 [claude | 3fa2]: filed upstream issue kuzudb/kuzu#4187',
      ] }),
  T(251, 'Windows CI for board_os CLI',              'cli',      'chore',   'blocked', 'P2', '4h', 'phase-l', {
      rotation: 0.4, blockedReason: 'GH Actions windows-latest runner flaking on flock emulation' }),

  // ========== COMPLETE ==========
  T(260, 'Phase I.3 — cos_graph_context MCP tool',         'graph_os',   'feature', 'complete', 'P0', '1d', 'phase-i',  { rotation: -0.7 }),
  T(261, 'SQLite backend as default graph store',          'graph_os',   'feature', 'complete', 'P0', '2d', 'phase-i',  { rotation: 1.0 }),
  T(262, 'cos_search observation boosts',                  'thinking_os','feature', 'complete', 'P1', '4h', 'phase-k',  { rotation: -0.2 }),
  T(263, 'Rule 14 envelope compliance audit',              'core',       'chore',   'complete', 'P1', '3h', null,       { rotation: 0.9 }),
  T(264, 'Doctor check C19 — graph_os sync lag',           'core',       'test',    'complete', 'P2', '2h', 'phase-i',  { rotation: -1.2 }),

  // ========== ARCHIVE ==========
  T(270, 'Legacy 12-section template (pre-L)',             'templates',  'refactor','archive', 'P3', '—',  null,        { rotation: 0.3 }),
  T(271, 'Phase C tasks table (superseded by v13)',        'board_os',   'refactor','archive', 'P3', '—',  null,        { rotation: -0.6 }),
];

// live work-log stream (agent-surface overlay)
const LIVE_STREAM = [
  { t: '14:02:11', agent: 'claude', kind: 'work_log',  task: 'TASK-230', msg: 'optimistic concurrency (R-L-29) prototype — reading current status pre-write works' },
  { t: '14:01:58', agent: 'claude', kind: 'hook',      task: 'TASK-230', msg: 'capture-work-log.sh → flock acquired (78ms)' },
  { t: '14:01:44', agent: 'codex',  kind: 'work_log',  task: 'TASK-231', msg: 'Sortable group="cards" across lanes; ghost preview landing OK' },
  { t: '14:00:51', agent: 'codex',  kind: 'transition',task: 'TASK-231', msg: 'ready → in_progress (WIP warn: 2/1)' },
  { t: '14:00:49', agent: 'codex',  kind: 'hook',      task: 'TASK-231', msg: 'enforce-wip-limit.sh → WARN (not blocking, override=0)' },
  { t: '13:58:02', agent: 'human',  kind: 'transition',task: 'TASK-242', msg: 'in_progress → testing' },
  { t: '13:52:17', agent: 'claude', kind: 'search',    task: 'TASK-230', msg: 'cos_search("WIP cap optimistic concurrency") → 4 prior observations' },
  { t: '13:49:30', agent: 'claude', kind: 'pick',      task: null,        msg: 'cos_task_pick() → [TASK-230 P0, TASK-220 emergency, TASK-210 P0]' },
];

window.SWIMLANES = SWIMLANES;
window.COLUMNS = COLUMNS;
window.KIND_COLORS = KIND_COLORS;
window.EPICS = EPICS;
window.AGENTS = AGENTS;
window.TASKS = TASKS;
window.LIVE_STREAM = LIVE_STREAM;
