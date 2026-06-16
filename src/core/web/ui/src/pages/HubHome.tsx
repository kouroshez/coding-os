import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import LiveAgentsPanel from '@/features/cognition/LiveAgentsPanel';
import { apiDelete, apiPost } from '@/lib/api-client';
import { PageHeader, ActionPill, Banner, SkeletonGrid } from '@/layout/HubPrimitives';
import OnboardingWizard from './OnboardingWizard';

/**
 * Hub home page — the first screen when opening http://127.0.0.1:9188.
 *
 * PURPOSE: List every coding-os project + offer the CRUD you'd
 *          otherwise have to drop into the terminal for:
 *            - Import an existing .coding-os/ directory by path.
 *            - Scan a filesystem root for projects and import all hits.
 *            - Unregister a project (kebab menu on each card).
 *            - Garbage-collect entries whose directory no longer exists.
 *          Closes the "panel is read-only" gap — one screen for full
 *          project lifecycle without the CLI.
 * INPUT:   GET /api/hub/projects; POST /api/hub/registry/{add,scan,gc};
 *          DELETE /api/hub/registry/{slug}; GET /api/hub/suggest-roots.
 * OUTPUT:  A grid of project cards linking to /p/<slug>/board plus a
 *          toolbar with Import / Scan / GC actions.
 */

interface HubProject {
  slug: string;
  path: string;
  created_at?: string;
  source?: 'registry' | 'runtime-cwd' | string;
}

interface HubProjectsPayload {
  projects: HubProject[];
  count: number;
}

interface ScanHit {
  path: string;
  slug: string;
  already_registered: boolean;
}

interface ScanPayload {
  root: string;
  hits: ScanHit[];
  count: number;
  visited_dirs: number;
  hit_limit_reached: boolean;
  depth_limit_reached: boolean;
}

interface GcPayload {
  kept: { slug: string; path: string }[];
  removed: { slug: string; path: string }[];
  dry_run: boolean;
  kept_count: number;
  removed_count: number;
}

interface SuggestRootsPayload {
  suggestions: string[];
}

type ActionError = { action: string; message: string } | null;

function useBusy(): [boolean, <T>(fn: () => Promise<T>) => Promise<T>] {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  }, []);
  return [busy, run];
}

export default function HubHome() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading, error } = useApiGet<HubProjectsPayload>(
    ['hub-projects'],
    '/api/hub/projects',
  );
  const { data: roots } = useApiGet<SuggestRootsPayload>(
    ['hub-suggest-roots'],
    '/api/hub/suggest-roots',
  );

  const [importOpen, setImportOpen] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [actionError, setActionError] = useState<ActionError>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [busy, runBusy] = useBusy();

  const refresh = useCallback(async () => {
    await invalidateApiQueries(qc, '/api/hub/projects');
  }, [qc]);

  const runImport = useCallback(
    async (path: string, slug?: string) => {
      setActionError(null);
      try {
        const [added] = await runBusy(() =>
          apiPost<{ slug: string; path: string }>('/api/hub/registry/add', {
            path,
            slug: slug && slug.trim() ? slug.trim() : undefined,
          }),
        );
        await refresh();
        setActionNote(`imported ${added.slug} → ${added.path}`);
        setImportOpen(false);
      } catch (err) {
        setActionError({
          action: 'import',
          message: err instanceof Error ? err.message : 'import failed',
        });
      }
    },
    [refresh, runBusy],
  );

  const onWizardCreated = useCallback(
    async (slug: string) => {
      await refresh();
      setActionNote(`created ${slug}`);
      setNewOpen(false);
      if (slug) navigate(`/p/${encodeURIComponent(slug)}/workspace/chat`);
    },
    [refresh, navigate],
  );

  const runRemove = useCallback(
    async (slug: string) => {
      if (!window.confirm(
        `Unregister "${slug}" from the hub?\n\n`
        + 'This does NOT delete anything on disk — only removes the '
        + 'hub registry entry.  Re-add later via Import.',
      )) return;
      setActionError(null);
      try {
        await runBusy(() =>
          apiDelete<{ slug: string; path: string }>(`/api/hub/registry/${encodeURIComponent(slug)}`),
        );
        await refresh();
        setActionNote(`unregistered ${slug}`);
      } catch (err) {
        setActionError({
          action: 'remove',
          message: err instanceof Error ? err.message : 'remove failed',
        });
      }
    },
    [refresh, runBusy],
  );

  const runPrune = useCallback(
    async () => {
      setActionError(null);
      try {
        // Dry-run first so the user confirms against the actual list, mirroring
        // the per-project Unregister confirm — registry GC is irreversible.
        const [preview] = await runBusy(() =>
          apiPost<GcPayload>('/api/hub/registry/gc', { dry_run: true }),
        );
        const n = preview.removed_count;
        if (n === 0) {
          setActionNote('registry is already clean; nothing to prune.');
          return;
        }
        const ok = window.confirm(
          `Prune ${n} stale entr${n === 1 ? 'y' : 'ies'} from the hub registry?\n\n`
          + preview.removed.map((r) => `• ${r.slug} → ${r.path}`).join('\n')
          + '\n\nThis only removes registry entries — nothing on disk is deleted.',
        );
        if (!ok) {
          setActionNote('prune cancelled.');
          return;
        }
        const [result] = await runBusy(() =>
          apiPost<GcPayload>('/api/hub/registry/gc', { dry_run: false }),
        );
        await refresh();
        const removed = result.removed_count;
        setActionNote(`removed ${removed} stale entr${removed === 1 ? 'y' : 'ies'}`);
      } catch (err) {
        setActionError({
          action: 'prune',
          message: err instanceof Error ? err.message : 'prune failed',
        });
      }
    },
    [refresh, runBusy],
  );

  const [query, setQuery] = useState('');
  const projects = data?.projects ?? [];
  const filteredProjects = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter(
      (p) =>
        p.slug.toLowerCase().includes(q) ||
        p.path.toLowerCase().includes(q),
    );
  }, [projects, query]);
  const projectCount = projects.length;

  return (
    <div className="relative flex h-full flex-col overflow-auto cos-scroll">
      <div className="mx-auto w-full max-w-7xl px-6 pb-12 pt-10 sm:px-10">
        <PageHeader
          eyebrow={(
            <>
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--cos-ok-tint)] shadow-[0_0_8px]" />
              Hub · port 9188
            </>
          )}
          title="Your projects"
          subtitle={(
            <>
              Open a project to work in it — chat, board, graph, or search.
              Register an existing <code className="rounded bg-[var(--cos-panel)] px-1 py-0.5 text-[11px]">.coding-os/</code> folder,
              scan a directory, or prune stale entries.
            </>
          )}
          right={(
            <div className="flex shrink-0 items-center gap-3 rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/70 px-4 py-3 backdrop-blur">
              <div className="text-center">
                <div className="text-2xl font-semibold tabular-nums text-[var(--accent)]">
                  {projectCount}
                </div>
                <div className="text-[10px] tracking-wide text-[var(--cos-muted)]">
                  {projectCount === 1 ? 'project' : 'projects'}
                </div>
              </div>
            </div>
          )}
          actions={(
            <>
              <ActionPill
                icon={<IconPlus />}
                label="New project"
                onClick={() => { setNewOpen(true); setImportOpen(false); setScanOpen(false); }}
                primary
              />
              <ActionPill
                icon={<IconPlus />}
                label="Import existing"
                onClick={() => { setImportOpen(true); setNewOpen(false); setScanOpen(false); }}
              />
              <ActionPill
                icon={<IconFolderSearch />}
                label="Scan folder"
                onClick={() => { setScanOpen(true); setImportOpen(false); setNewOpen(false); }}
              />
              <ActionPill
                icon={<IconBroom />}
                label="Prune dead entries"
                onClick={() => runPrune()}
                disabled={busy}
              />
              <ActionPill
                icon={<IconRefresh />}
                label="Refresh"
                onClick={() => refresh()}
                disabled={busy}
              />
            </>
          )}
        />

        {/* Notes + errors */}
        {actionNote && (
          <Banner kind="ok" onDismiss={() => setActionNote(null)}>{actionNote}</Banner>
        )}
        {actionError && (
          <Banner kind="error" onDismiss={() => setActionError(null)}>
            [{actionError.action}] {actionError.message}
          </Banner>
        )}

        {/* Dialogs (Import / Scan inline; New = full-screen wizard, TASK-358) */}
        {newOpen && (
          <OnboardingWizard
            suggestions={roots?.suggestions ?? []}
            onClose={() => setNewOpen(false)}
            onCreated={onWizardCreated}
          />
        )}
        {importOpen && (
          <ImportDialog
            suggestions={roots?.suggestions ?? []}
            onCancel={() => setImportOpen(false)}
            onSubmit={runImport}
            busy={busy}
          />
        )}
        {scanOpen && (
          <ScanDialog
            suggestions={roots?.suggestions ?? []}
            onCancel={() => setScanOpen(false)}
            afterRegister={async (slugs) => {
              await refresh();
              setScanOpen(false);
              if (slugs.length > 0) {
                setActionNote(`imported ${slugs.length} project(s): ${slugs.join(', ')}`);
              } else {
                setActionNote('scan complete — no new projects registered.');
              }
            }}
          />
        )}

        {/* Loading / error / empty / grid */}
        {isLoading && <SkeletonGrid />}
        {error && (
          <p role="alert" className="text-sm text-[var(--cos-err)]">
            {error.message}
          </p>
        )}
        {!isLoading && !error && projectCount === 0 && (
          <EmptyState
            onImport={() => { setImportOpen(true); setScanOpen(false); }}
            onScan={() => { setScanOpen(true); setImportOpen(false); }}
          />
        )}
        {!isLoading && !error && projectCount > 0 && (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-[var(--cos-muted)]">
                {query ? (
                  <>
                    {filteredProjects.length} of {projectCount} match{' '}
                    <span className="font-mono">{`"${query}"`}</span>
                  </>
                ) : (
                  `${projectCount} ${projectCount === 1 ? 'project' : 'projects'}`
                )}
              </div>
              <div className="flex items-center gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-panel)] px-3 py-1.5">
                <IconSearch />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter projects…"
                  aria-label="Filter projects"
                  className="w-44 bg-transparent text-xs text-[var(--cos-text)] placeholder-[var(--cos-muted)] outline-none"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery('')}
                    className="text-[var(--cos-muted)] hover:text-[var(--cos-text)]"
                    aria-label="Clear filter"
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
            <ul className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
              {filteredProjects.map((p) => (
                <li key={`${p.slug}-${p.path}`}>
                  <ProjectCard
                    project={p}
                    onOpen={(feature) =>
                      navigate(`/p/${encodeURIComponent(p.slug)}/${feature}`)
                    }
                    onRemove={
                      p.source === 'runtime-cwd'
                        ? undefined
                        : () => runRemove(p.slug)
                    }
                  />
                </li>
              ))}
            </ul>
            {filteredProjects.length === 0 && query && (
              <div className="rounded-xl border border-dashed border-[var(--cos-border)] bg-[var(--cos-panel)]/40 p-10 text-center text-sm text-[var(--cos-muted)]">
                No project matches <span className="font-mono">{`"${query}"`}</span>.
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="ml-2 text-[var(--accent)] underline-offset-2 hover:underline"
                >
                  clear filter
                </button>
              </div>
            )}
          </>
        )}

        {/* Live agents — secondary "what's running right now" strip, below the
            primary project launcher (returns null when nothing is running). */}
        <div className="mt-12">
          <LiveAgentsPanel />
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Visual primitives (modernised look — pure presentation, no logic)
// --------------------------------------------------------------------------

function EmptyState({ onImport, onScan }: { onImport: () => void; onScan: () => void }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-gradient-to-br from-[var(--cos-panel)] to-[var(--cos-panel)]/40 p-10">
      <div className="mx-auto max-w-xl text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-bg)]/60 text-[var(--accent)]">
          <IconBox />
        </div>
        <h2 className="mb-2 text-lg font-semibold text-[var(--cos-text)]">No projects yet</h2>
        <p className="mb-5 text-sm text-[var(--cos-muted)]">
          Register a folder that already has coding-os set up, or scan a directory to add
          several at once.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <ActionPill icon={<IconPlus />} label="Import existing" onClick={onImport} primary />
          <ActionPill icon={<IconFolderSearch />} label="Scan folder" onClick={onScan} />
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Icons (inline SVG — no extra deps)
// --------------------------------------------------------------------------

const stroke = { strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
function IconFolderSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v3" />
      <circle cx="15.5" cy="15.5" r="3.5" />
      <path d="m21 21-2.5-2.5" />
    </svg>
  );
}
function IconBroom() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M19 4 8.5 14.5" />
      <path d="m13 9 2 2" />
      <path d="M14 17.5C10 21.5 4.5 19.5 4.5 19.5s-1-5.5 3-9.5l8 8Z" />
    </svg>
  );
}
function IconRefresh() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
      <path d="M21 4v4h-4" />
      <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
      <path d="M3 20v-4h4" />
    </svg>
  );
}
function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
function IconBox() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3.3 7 12 3l8.7 4" />
      <path d="M3.3 7 12 11l8.7-4" />
      <path d="M12 11v10" />
      <path d="M3.3 7v10L12 21" />
      <path d="M20.7 7v10L12 21" />
    </svg>
  );
}
const PROJECT_SHORTCUTS = [
  { key: 'chat', label: 'Chat', path: 'workspace/chat' },
  { key: 'board', label: 'Board', path: 'workspace/board' },
  { key: 'graph', label: 'Graph', path: 'graph' },
  { key: 'search', label: 'Search', path: 'workspace/search' },
] as const;

function FeatureIcon({ name }: { name: 'chat' | 'board' | 'graph' | 'search' }) {
  const props = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', ...stroke };
  switch (name) {
    case 'chat':
      return (
        <svg {...props}><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8A8.5 8.5 0 0 1 12.5 20a8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" /></svg>
      );
    case 'board':
      return (
        <svg {...props}><rect x="3" y="3" width="7" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="11" rx="1.5" /></svg>
      );
    case 'graph':
      return (
        <svg {...props}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8 7.5 16 7.5M7.5 8 12 16M16.5 8 12 16" /></svg>
      );
    case 'search':
      return <IconSearch />;
  }
}

// --------------------------------------------------------------------------
// Subcomponents
// --------------------------------------------------------------------------

function ProjectCard({
  project, onOpen, onRemove,
}: {
  project: HubProject;
  onOpen: (feature: string) => void;
  onRemove?: () => void;
}) {
  const [kebabOpen, setKebabOpen] = useState(false);
  const kebabRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!kebabOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!kebabRef.current?.contains(e.target as Node)) setKebabOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [kebabOpen]);

  const initial = project.slug.charAt(0).toUpperCase();

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)]/60 hover:shadow-xl hover:shadow-black/10">
      {/* Top accent bar */}
      <div className="h-1 bg-[var(--accent)]/70" aria-hidden="true" />

      {/* Header */}
      <div className="flex items-start justify-between gap-3 px-4 pb-3 pt-4">
        <Link
          to={`/p/${encodeURIComponent(project.slug)}/workspace/chat`}
          className="flex min-w-0 flex-1 items-center gap-3"
          title={`Open ${project.slug} — chat`}
        >
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/15 text-base font-semibold text-[var(--accent)]"
            aria-hidden="true"
          >
            {initial}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-[var(--cos-text)] group-hover:text-[var(--accent)]">
                {project.slug}
              </span>
              {project.source === 'runtime-cwd' && (
                <span
                  className="rounded-full border border-[var(--cos-ok)] bg-[var(--cos-ok-tint)] px-2 py-[1px] text-[9px] font-medium tracking-wide text-[var(--cos-ok)]"
                  title="Not in registry.json — auto-surfaced from the Hub's cwd."
                >
                  live cwd
                </span>
              )}
            </div>
            <div className="truncate text-[11px] text-[var(--cos-muted)]" title={project.path}>
              {project.path}
            </div>
          </div>
        </Link>

        <div ref={kebabRef} className="relative shrink-0">
          <button
            type="button"
            aria-label={`More actions for ${project.slug}`}
            aria-haspopup="menu"
            aria-expanded={kebabOpen}
            onClick={() => setKebabOpen((v) => !v)}
            className="rounded-lg p-1.5 text-[var(--cos-muted)] transition-colors hover:bg-[var(--board-grain)] hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" /></svg>
          </button>
          {kebabOpen && (
            <div
              role="menu"
              className="absolute right-0 top-[calc(100%+4px)] z-40 w-[220px] overflow-hidden rounded-xl border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-2xl"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  navigator.clipboard?.writeText(project.path).catch(() => undefined);
                  setKebabOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs hover:bg-[var(--board-grain)]"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg>
                Copy path
              </button>
              {onRemove && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setKebabOpen(false); onRemove(); }}
                  className="flex w-full items-center gap-2 border-t border-[var(--cos-border)] px-3 py-2.5 text-left text-xs text-[var(--cos-err)] hover:bg-[var(--cos-err-tint)]"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="M19 6 18 20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /></svg>
                  Unregister from hub
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Feature shortcuts — Chat is the default landing, then Board/Graph/Search */}
      <div className="grid grid-cols-4 gap-1 border-t border-[var(--cos-border)] bg-[var(--cos-bg)]/30 p-2">
        {PROJECT_SHORTCUTS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => onOpen(s.path)}
            className="group/feat flex flex-col items-center gap-1 rounded-lg px-2 py-2 text-[10px] font-medium text-[var(--cos-muted)] transition-all hover:bg-[var(--cos-panel)] hover:text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            <span className="opacity-70 group-hover/feat:opacity-100">
              <FeatureIcon name={s.key} />
            </span>
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      {project.created_at && (
        <div className="border-t border-[var(--cos-border)] px-4 py-1.5 text-[10px] tracking-wide text-[var(--cos-muted)]/80">
          Registered {project.created_at.slice(0, 10)}
        </div>
      )}
    </div>
  );
}

export function slugifyProjectName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '');
}

function ImportDialog({
  suggestions, onCancel, onSubmit, busy,
}: {
  suggestions: string[];
  onCancel: () => void;
  onSubmit: (path: string, slug?: string) => void | Promise<void>;
  busy: boolean;
}) {
  const [path, setPath] = useState('');
  const [slug, setSlug] = useState('');

  return (
    <section className="mb-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-4">
      <h2 className="mb-2 text-sm font-semibold text-[var(--cos-text)]">
        Import an existing coding-os project
      </h2>
      <p className="mb-3 text-xs text-[var(--cos-muted)]">
        The folder must already contain <code>.coding-os/</code>.  For a
        brand-new project, run <code>cos init</code> in the folder first
        (programmatic scaffolding from the panel is a follow-up).
      </p>
      <label className="mb-2 block text-xs">
        <span className="mb-1 block text-[var(--cos-muted)]">Absolute path</span>
        <input
          type="text"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="/Users/you/code/my-app"
          className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)]"
        />
      </label>
      {suggestions.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1 text-[10px]">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setPath(s)}
              className="rounded border border-[var(--cos-border)] px-2 py-0.5 font-mono text-[var(--cos-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              title={`Prefill with ${s}`}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <label className="mb-3 block text-xs">
        <span className="mb-1 block text-[var(--cos-muted)]">
          Slug override (optional — defaults to directory name)
        </span>
        <input
          type="text"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="my-app"
          className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)]"
        />
      </label>
      <div className="flex items-center gap-2">
        <ActionPill
          primary
          label={busy ? 'importing…' : 'Import'}
          onClick={() => {
            if (!path.trim()) return;
            void onSubmit(path.trim(), slug || undefined);
          }}
          disabled={busy || !path.trim()}
        />
        <ActionPill label="Cancel" onClick={onCancel} disabled={busy} />
      </div>
    </section>
  );
}

function ScanDialog({
  suggestions, onCancel, afterRegister,
}: {
  suggestions: string[];
  onCancel: () => void;
  afterRegister: (registeredSlugs: string[]) => void | Promise<void>;
}) {
  const [root, setRoot] = useState(suggestions[0] ?? '');
  const [hits, setHits] = useState<ScanHit[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, runBusy] = useBusy();
  const [err, setErr] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);

  const scannable = useMemo(() => root.trim().length > 0, [root]);

  const runScan = useCallback(async () => {
    setErr(null);
    setMeta(null);
    try {
      const [payload] = await runBusy(() =>
        apiPost<ScanPayload>('/api/hub/registry/scan', {
          root: root.trim(),
          max_depth: 6,
          limit: 100,
        }),
      );
      setHits(payload.hits);
      const pre = new Set<string>();
      for (const h of payload.hits) {
        if (!h.already_registered) pre.add(h.path);
      }
      setSelected(pre);
      setMeta(
        `scanned ${payload.visited_dirs} dir(s) under ${payload.root} · `
        + `${payload.count} hit(s)`
        + (payload.hit_limit_reached ? ' · hit-limit reached' : '')
        + (payload.depth_limit_reached ? ' · depth-limit reached' : ''),
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'scan failed');
    }
  }, [root, runBusy]);

  const toggle = (path: string) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const importSelected = useCallback(async () => {
    setErr(null);
    const registered: string[] = [];
    for (const hit of hits ?? []) {
      if (!selected.has(hit.path) || hit.already_registered) continue;
      try {
        const [resp] = await apiPost<{ slug: string }>(
          '/api/hub/registry/add',
          { path: hit.path },
        );
        registered.push(resp.slug);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'failed';
        setErr(`${hit.path}: ${msg}`);
      }
    }
    await afterRegister(registered);
  }, [hits, selected, afterRegister]);

  return (
    <section className="mb-4 rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-4">
      <h2 className="mb-2 text-sm font-semibold text-[var(--cos-text)]">
        Scan a folder for coding-os projects
      </h2>
      <p className="mb-3 text-xs text-[var(--cos-muted)]">
        Read-only — pick which hits to register. Skips noise dirs
        (<code>node_modules</code>, <code>.venv</code>, <code>.git</code>, …).
      </p>
      <label className="mb-2 block text-xs">
        <span className="mb-1 block text-[var(--cos-muted)]">Root directory</span>
        <input
          type="text"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          placeholder="/Users/you/code"
          className="w-full rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)]"
        />
      </label>
      {suggestions.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1 text-[10px]">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setRoot(s)}
              className="rounded border border-[var(--cos-border)] px-2 py-0.5 font-mono text-[var(--cos-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="mb-3 flex items-center gap-2">
        <ActionPill
          primary
          label={busy ? 'scanning…' : 'Scan'}
          onClick={() => void runScan()}
          disabled={busy || !scannable}
        />
        <ActionPill label="Cancel" onClick={onCancel} disabled={busy} />
      </div>

      {meta && <div className="mb-2 text-[11px] text-[var(--cos-muted)]">{meta}</div>}
      {err && <div className="mb-2 text-xs text-[var(--cos-err)]">{err}</div>}

      {hits && hits.length === 0 && (
        <p className="text-xs text-[var(--cos-muted)]">
          No projects found under that root.
        </p>
      )}
      {hits && hits.length > 0 && (
        <>
          <ul className="mb-3 max-h-[320px] divide-y divide-[var(--cos-border)] overflow-auto cos-scroll rounded border border-[var(--cos-border)]">
            {hits.map((h) => (
              <li key={h.path}>
                <label className={[
                  'flex cursor-pointer items-start gap-3 px-3 py-2 text-xs transition-colors',
                  h.already_registered
                    ? 'opacity-60'
                    : 'hover:bg-[var(--board-grain)]',
                ].join(' ')}>
                  <input
                    type="checkbox"
                    checked={selected.has(h.path)}
                    disabled={h.already_registered}
                    onChange={() => toggle(h.path)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-[var(--cos-text)]">{h.slug}</span>
                      {h.already_registered && (
                        <span className="rounded border border-[var(--cos-border)] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
                          already registered
                        </span>
                      )}
                    </div>
                    <div className="break-all font-mono text-[10px] text-[var(--cos-muted)]">
                      {h.path}
                    </div>
                  </div>
                </label>
              </li>
            ))}
          </ul>
          <ActionPill
            primary
            label={`Import selected (${selected.size})`}
            onClick={() => void importSelected()}
            disabled={busy || selected.size === 0}
          />
        </>
      )}
    </section>
  );
}
