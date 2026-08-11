import { useCallback, useMemo, useState } from 'react';
import { apiPost } from '@/lib/api-client';
import { ActionPill } from '@/layout/HubPrimitives';
import type { ScanHit, ScanPayload } from './hub-home-types';
import { useBusy } from './hub-home-shared';

export function ImportDialog({
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
        The folder must already contain <code>.coding-os/</code>. To scaffold a
        brand-new project instead, use <strong>New project</strong>.
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

export function ScanDialog({
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
