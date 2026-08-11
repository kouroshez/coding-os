import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { HubProject } from './hub-home-types';
import { FeatureIcon } from './HubIcons';
import { PROJECT_SHORTCUTS, stroke } from './hub-home-shared';

export function ProjectCard({
  project, onOpen, onRemove, onRename,
}: {
  project: HubProject;
  onOpen: (feature: string) => void;
  onRemove?: () => void;
  onRename?: () => void;
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
              {onRename && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setKebabOpen(false); onRename(); }}
                  className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs hover:bg-[var(--board-grain)]"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
                  Rename slug
                </button>
              )}
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

