import { Section } from './DoctorPrimitives';
import type { HealthPayload } from './doctor-types';

export function MaintenanceTab({ health }: { health: HealthPayload | undefined }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Section title="Repair commands">
        <ul className="space-y-2 text-[11px]">
          <li>
            <span className="text-[var(--cos-muted)]">backend degraded → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos graph-reindex --force</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">stale index → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos graph-reindex</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">full system check → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos doctor</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">restart hub → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos hub stop && cos hub start</code>
          </li>
          <li>
            <span className="text-[var(--cos-muted)]">tail hub log → </span>
            <code className="rounded bg-[var(--cos-grain)] px-1 font-mono">cos hub logs</code>
          </li>
        </ul>
      </Section>
      <Section title="Quick links">
        <ul className="space-y-1 text-[11px]">
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/metrics" target="_blank" rel="noreferrer">
              /metrics (Prometheus text)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/docs" target="_blank" rel="noreferrer">
              /docs (OpenAPI Swagger)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/openapi.json" target="_blank" rel="noreferrer">
              /openapi.json
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/health" target="_blank" rel="noreferrer">
              /health (raw JSON)
            </a>
          </li>
          <li>
            <a className="text-[var(--cos-accent)] hover:underline" href="/redoc" target="_blank" rel="noreferrer">
              /redoc (alt API docs)
            </a>
          </li>
        </ul>
      </Section>
      <Section title="Reported by /health" cols="md:col-span-2">
        {health ? (
          <pre className="cos-scroll max-h-64 overflow-auto rounded bg-[var(--cos-grain,#f4efe1)]/40 p-2 text-[10px] leading-tight">
            {JSON.stringify(health, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-[var(--cos-muted)]">no health payload.</p>
        )}
      </Section>
    </div>
  );
}

// ----- shared atoms --------------------------------------------------
