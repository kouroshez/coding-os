import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useApiGet } from '@/lib/hooks';
import { projectFeaturePath } from '@/lib/use-scoped-link';

interface HubProject {
  slug: string;
  path: string;
  source?: string;
}
interface HubProjectsPayload {
  projects: HubProject[];
  count: number;
}

const FEATURE_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  board: 'Board',
  graph: 'Graph',
  search: 'Search',
  cognition: 'Cognition',
};

export default function NeedProjectPage({ feature }: { feature: string }) {
  const navigate = useNavigate();
  const params = useParams<{ sessionId?: string; rootUid?: string }>();
  const { search } = useLocation();
  const { data, isLoading, error } = useApiGet<HubProjectsPayload>(
    ['hub-projects'],
    '/api/hub/projects',
  );
  const projects = data?.projects ?? [];
  const featureLabel = FEATURE_LABELS[feature] ?? feature;
  // Preserve the deep-link target the user clicked (a cognition :sessionId or
  // graph :rootUid + ?view=… query) across the project pick, so picking a
  // project lands on the actual transcript/node — not a bare feature tab.
  const subId = params.sessionId ?? params.rootUid ?? null;

  const choose = (slug: string) => {
    const sub = subId ? `/${encodeURIComponent(subId)}` : '';
    navigate(`${projectFeaturePath(feature, slug)}${sub}${search}`, { replace: true });
  };

  return (
    <div className="flex h-full min-h-0 items-center justify-center p-8">
      <div className="w-full max-w-xl rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)] p-6 shadow-xl">
        <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-[var(--cos-border)] bg-[var(--cos-bg)] px-3 py-1 text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--cos-muted)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--cos-warn-tint)] shadow-[0_0_8px] " />
          project required
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-[var(--cos-text)]">
          Pick a project to open <span className="text-[var(--cos-accent)]">{featureLabel}</span>
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--cos-muted)]">
          This panel is scoped to a single coding-os project. Choose one
          below and you&apos;ll land on its <strong>{featureLabel}</strong> tab.
          You can switch projects later via the header dropdown.
        </p>

        {isLoading && (
          <div className="mt-6 text-sm text-[var(--cos-muted)]">Loading projects…</div>
        )}
        {error && (
          <div role="alert" className="mt-6 text-sm text-[var(--cos-err)]">
            Failed to load projects: {error.message}
          </div>
        )}
        {!isLoading && !error && projects.length === 0 && (
          <div className="mt-6 rounded border border-dashed border-[var(--cos-border)] p-4 text-sm text-[var(--cos-muted)]">
            No projects registered yet.{' '}
            <button
              type="button"
              onClick={() => navigate('/', { replace: true })}
              className="font-semibold text-[var(--cos-accent)] underline"
            >
              Go to Hub home
            </button>{' '}
            and import one.
          </div>
        )}

        {projects.length > 0 && (
          <ul className="mt-6 flex flex-col gap-2">
            {projects.map((p) => (
              <li key={p.slug}>
                <button
                  type="button"
                  onClick={() => choose(p.slug)}
                  className="group flex w-full items-center justify-between gap-3 rounded-lg border border-[var(--cos-border)] bg-[var(--cos-bg)] px-4 py-3 text-left transition-colors hover:border-[var(--cos-accent)] hover:bg-[var(--cos-grain)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                >
                  <div className="min-w-0">
                    <div className="truncate font-mono text-sm font-semibold text-[var(--cos-text)]">
                      {p.slug}
                    </div>
                    <div className="truncate text-[11px] text-[var(--cos-muted)]" dir="ltr">
                      {p.path}
                    </div>
                  </div>
                  <span className="shrink-0 text-[10px] font-mono uppercase tracking-wider text-[var(--cos-muted)] group-hover:text-[var(--cos-accent)]">
                    open →
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6 flex items-center justify-between gap-3 text-[11px] text-[var(--cos-muted)]">
          <button
            type="button"
            onClick={() => navigate('/', { replace: true })}
            className="rounded px-2 py-1 hover:bg-[var(--cos-grain)] hover:text-[var(--cos-text)]"
          >
            ← All projects (Hub home)
          </button>
          <span className="font-mono">{projects.length} registered</span>
        </div>
      </div>
    </div>
  );
}
