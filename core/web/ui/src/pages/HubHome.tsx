import { Link } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';

/**
 * Hub home page — the first screen when opening http://127.0.0.1:9188.
 *
 * PURPOSE: List every coding-os project registered in ~/.coding-os/
 *          registry.json and let the user deep-link into each one.
 * INPUT:   GET /api/hub/projects.
 * OUTPUT:  A grid of project cards linking to /p/<slug>/board.
 */

interface HubProject {
  slug: string;
  path: string;
  created_at: string;
}

interface HubProjectsPayload {
  projects: HubProject[];
  count: number;
}

export default function HubHome() {
  const { data, isLoading, error } = useApiGet<HubProjectsPayload>(
    ['hub-projects'],
    '/api/hub/projects',
  );

  return (
    <div className="flex h-full flex-col overflow-auto p-8 cos-scroll">
      <header className="mb-6">
        <h1
          className="text-2xl font-semibold text-[var(--accent)]"
          style={{ fontFamily: "'Permanent Marker', cursive" }}
        >
          Your coding-os projects
        </h1>
        <p className="mt-1 text-sm text-[var(--cos-muted)]">
          Pick a project to open its board, graph, search, or cognition view.
        </p>
      </header>

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
            Run <code>cos init</code> inside a project directory to add it here.
          </p>
        </div>
      )}
      {!isLoading && !error && data && data.projects.length > 0 && (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.projects.map((p) => (
            <li key={p.slug}>
              <Link
                to={`/p/${encodeURIComponent(p.slug)}/board`}
                className="block rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-4 transition-colors hover:border-[var(--cos-accent)]"
              >
                <div className="mb-1 font-semibold text-[var(--cos-text)]">{p.slug}</div>
                <div className="break-all font-mono text-xs text-[var(--cos-muted)]">
                  {p.path}
                </div>
                {p.created_at && (
                  <div className="mt-2 text-[10px] uppercase tracking-wide text-[var(--cos-muted)]">
                    registered {p.created_at.slice(0, 10)}
                  </div>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
