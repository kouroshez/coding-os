import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import LiveAgentsPanel from '@/features/cognition/LiveAgentsPanel';
import { apiDelete, apiPatch, apiPost } from '@/lib/api-client';
import { PageHeader, ActionPill, Banner, SkeletonGrid } from '@/layout/HubPrimitives';
import OnboardingWizard, { readParkedJob } from './OnboardingWizard';
import type {
  GcPayload,
  HubProjectsPayload,
  SuggestRootsPayload,
} from './hub-home/hub-home-types';
import { slugifyProjectName, useBusy } from './hub-home/hub-home-shared';
import {
  IconBox,
  IconBroom,
  IconFolderSearch,
  IconPlus,
  IconRefresh,
  IconSearch,
} from './hub-home/HubIcons';
import { ProjectCard } from './hub-home/ProjectCard';
import { ImportDialog, ScanDialog } from './hub-home/HubDialogs';

// Re-exported for OnboardingWizard.test.tsx, which imports it from here.
export { slugifyProjectName };
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

type ActionError = { action: string; message: string } | null;

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
  // Re-open the Composer when a create is still in flight from a previous page
  // load — the wizard owns the re-attach, but it can only do that once mounted.
  const [newOpen, setNewOpen] = useState(() => readParkedJob() !== '');
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

  const runRename = useCallback(
    async (slug: string) => {
      const next = window.prompt(
        `Rename "${slug}" in the hub registry?\n\n`
        + 'Lowercase letters, digits, dot, dash, underscore. The folder on disk is untouched.',
        slug,
      );
      const wanted = (next ?? '').trim();
      if (!wanted || wanted === slug) return;
      setActionError(null);
      try {
        const [entry] = await runBusy(() =>
          apiPatch<{ slug: string; path: string }>(
            `/api/hub/registry/${encodeURIComponent(slug)}`,
            { new_slug: wanted },
          ),
        );
        await refresh();
        setActionNote(`renamed to ${entry?.slug ?? wanted}`);
      } catch (err) {
        setActionError({
          action: 'rename',
          message: err instanceof Error ? err.message : 'rename failed',
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
            suggestions={roots?.scaffoldable ?? roots?.suggestions ?? []}
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
            onCreate={() => { setNewOpen(true); setImportOpen(false); setScanOpen(false); }}
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
                    onRename={
                      p.source === 'runtime-cwd'
                        ? undefined
                        : () => runRename(p.slug)
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

function EmptyState({
  onCreate,
  onImport,
  onScan,
}: {
  onCreate: () => void;
  onImport: () => void;
  onScan: () => void;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-gradient-to-br from-[var(--cos-panel)] to-[var(--cos-panel)]/40 p-10">
      <div className="mx-auto max-w-xl text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-bg)]/60 text-[var(--accent)]">
          <IconBox />
        </div>
        <h2 className="mb-2 text-lg font-semibold text-[var(--cos-text)]">Start your first project</h2>
        <p className="mb-5 text-sm text-[var(--cos-muted)]">
          Pick a stack and coding-os scaffolds the project for you — docs, board, and agent
          setup included. Already have one? Import the folder or scan a directory instead.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <ActionPill icon={<IconPlus />} label="New project" onClick={onCreate} primary />
          <ActionPill icon={<IconPlus />} label="Import existing" onClick={onImport} />
          <ActionPill icon={<IconFolderSearch />} label="Scan folder" onClick={onScan} />
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Icons (inline SVG — no extra deps)
// --------------------------------------------------------------------------

