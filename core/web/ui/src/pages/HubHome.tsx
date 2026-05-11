import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiDelete, apiPost } from '@/lib/api-client';

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

  const runGc = useCallback(
    async (dryRun: boolean) => {
      setActionError(null);
      try {
        const [result] = await runBusy(() =>
          apiPost<GcPayload>('/api/hub/registry/gc', { dry_run: dryRun }),
        );
        await refresh();
        const n = result.removed_count;
        const verb = dryRun ? 'would remove' : 'removed';
        setActionNote(
          n === 0
            ? 'registry is already clean; nothing to prune.'
            : `${verb} ${n} stale entr${n === 1 ? 'y' : 'ies'}`,
        );
      } catch (err) {
        setActionError({
          action: 'gc',
          message: err instanceof Error ? err.message : 'gc failed',
        });
      }
    },
    [refresh, runBusy],
  );

  return (
    <div className="flex h-full flex-col overflow-auto p-8 cos-scroll">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1
            className="text-2xl font-semibold text-[var(--accent)]"
            style={{ fontFamily: "'Permanent Marker', cursive" }}
          >
            Your coding-os projects
          </h1>
          <p className="mt-1 text-sm text-[var(--cos-muted)]">
            Pick a project to open its board, graph, search, or cognition —
            or import / scan / prune from the toolbar.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ToolbarButton
            label="+ Import existing"
            onClick={() => { setImportOpen(true); setScanOpen(false); }}
            primary
          />
          <ToolbarButton
            label="Scan folder"
            onClick={() => { setScanOpen(true); setImportOpen(false); }}
          />
          <ToolbarButton
            label="Prune dead entries"
            onClick={() => runGc(false)}
            disabled={busy}
          />
          <ToolbarButton
            label="Refresh"
            onClick={() => refresh()}
            disabled={busy}
          />
        </div>
      </header>

      {actionNote && (
        <div className="mb-4 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {actionNote}
          <button
            type="button"
            className="ml-3 underline opacity-70 hover:opacity-100"
            onClick={() => setActionNote(null)}
          >
            dismiss
          </button>
        </div>
      )}
      {actionError && (
        <div className="mb-4 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          [{actionError.action}] {actionError.message}
          <button
            type="button"
            className="ml-3 underline opacity-70 hover:opacity-100"
            onClick={() => setActionError(null)}
          >
            dismiss
          </button>
        </div>
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

      {isLoading && (
        <p className="text-sm text-[var(--cos-muted)]">loading registry…</p>
      )}
      {error && (
        <p role="alert" className="text-sm text-rose-500">
          {error.message}
        </p>
      )}
      {!isLoading && !error && data && data.projects.length === 0 && (
        <div className="rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] p-6 text-sm">
          <p className="mb-2 font-semibold">No projects registered yet.</p>
          <p className="text-[var(--cos-muted)]">
            Click <strong>+ Import existing</strong> to register a
            directory that already has <code>.coding-os/</code>, or{' '}
            <strong>Scan folder</strong> to pick up everything under
            <code> ~/code </code> / <code>~/Projects</code> at once.
          </p>
          <p className="mt-2 text-[var(--cos-muted)]">
            Starting a brand-new project still goes through the CLI:
            <code> cos init</code> inside the target directory.
          </p>
        </div>
      )}
      {!isLoading && !error && data && data.projects.length > 0 && (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.projects.map((p) => (
            <li key={`${p.slug}-${p.path}`}>
              <ProjectCard
                project={p}
                onOpen={(feature) =>
                  navigate(`/p/${encodeURIComponent(p.slug)}/${feature}`)
                }
                onRemove={
                  p.source === 'runtime-cwd'
                    ? undefined  // cwd-derived entry isn't on disk; can't be "removed"
                    : () => runRemove(p.slug)
                }
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Subcomponents
// --------------------------------------------------------------------------

function ToolbarButton({
  label, onClick, disabled, primary,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        'rounded border px-3 py-1.5 font-mono text-xs transition-colors',
        primary
          ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)] hover:bg-[var(--accent)]/20'
          : 'border-[var(--cos-border)] text-[var(--cos-text)] hover:border-[var(--accent)] hover:text-[var(--accent)]',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

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

  return (
    <div className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] transition-colors hover:border-[var(--cos-accent)]">
      <div className="flex items-start justify-between gap-2 border-b border-[var(--cos-border)] p-3">
        <Link
          to={`/p/${encodeURIComponent(project.slug)}`}
          className="min-w-0 flex-1"
        >
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold text-[var(--cos-text)]">
              {project.slug}
            </span>
            {project.source === 'runtime-cwd' && (
              <span
                className="rounded border border-[var(--cos-border)] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[var(--cos-muted)]"
                title="Not in registry.json — auto-surfaced from the Hub's cwd."
              >
                live cwd
              </span>
            )}
          </div>
          <div className="mt-1 break-all font-mono text-[11px] text-[var(--cos-muted)]">
            {project.path}
          </div>
        </Link>

        <div ref={kebabRef} className="relative shrink-0">
          <button
            type="button"
            aria-label={`More actions for ${project.slug}`}
            aria-haspopup="menu"
            aria-expanded={kebabOpen}
            onClick={() => setKebabOpen((v) => !v)}
            className="rounded p-1 text-[var(--cos-muted)] hover:bg-[var(--board-grain)] hover:text-[var(--cos-text)]"
          >
            ⋯
          </button>
          {kebabOpen && (
            <div
              role="menu"
              className="absolute right-0 top-[calc(100%+2px)] z-40 w-[200px] overflow-hidden rounded border border-[var(--cos-border)] bg-[var(--cos-panel)] shadow-lg"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  navigator.clipboard?.writeText(project.path).catch(() => undefined);
                  setKebabOpen(false);
                }}
                className="block w-full px-3 py-2 text-left text-xs hover:bg-[var(--board-grain)]"
              >
                Copy path
              </button>
              {onRemove && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setKebabOpen(false);
                    onRemove();
                  }}
                  className="block w-full border-t border-[var(--cos-border)] px-3 py-2 text-left text-xs text-rose-400 hover:bg-rose-500/10"
                >
                  Unregister from hub
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 divide-x divide-[var(--cos-border)] text-[10px] font-mono uppercase tracking-wider">
        {(['board', 'graph', 'search', 'cognition'] as const).map((feat) => (
          <button
            key={feat}
            type="button"
            onClick={() => onOpen(feat)}
            className="px-2 py-2 text-[var(--cos-muted)] transition-colors hover:bg-[var(--board-grain)] hover:text-[var(--accent)]"
          >
            {feat}
          </button>
        ))}
      </div>

      {project.created_at && (
        <div className="border-t border-[var(--cos-border)] px-3 py-1 text-[9px] uppercase tracking-wider text-[var(--cos-muted)]">
          registered {project.created_at.slice(0, 10)}
        </div>
      )}
    </div>
  );
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
        (programmatic scaffolding from the panel is Phase O.2 follow-up).
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
        <ToolbarButton
          primary
          label={busy ? 'importing…' : 'Import'}
          onClick={() => {
            if (!path.trim()) return;
            void onSubmit(path.trim(), slug || undefined);
          }}
          disabled={busy || !path.trim()}
        />
        <ToolbarButton label="Cancel" onClick={onCancel} disabled={busy} />
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
        <ToolbarButton
          primary
          label={busy ? 'scanning…' : 'Scan'}
          onClick={() => void runScan()}
          disabled={busy || !scannable}
        />
        <ToolbarButton label="Cancel" onClick={onCancel} disabled={busy} />
      </div>

      {meta && <div className="mb-2 text-[11px] text-[var(--cos-muted)]">{meta}</div>}
      {err && <div className="mb-2 text-xs text-rose-400">{err}</div>}

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
          <ToolbarButton
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
