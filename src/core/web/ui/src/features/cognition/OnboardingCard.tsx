import { useState } from 'react';
import { Rocket, X } from 'lucide-react';
import { useApiGet } from '@/lib/hooks';
import { apiPost } from '@/lib/api-client';

interface OnboardingStatus {
  complete: boolean;
  placeholders_remaining?: number;
  reason?: string;
  source?: string;
}

/**
 * Chat-landing hero shown when the project still has scaffold placeholders
 * (GET /api/cognition/onboarding-status). The CTA starts the docs-scoped
 * onboarder session. Dismissing persists to `.coding-os/onboarding.json` so the
 * hero stays gone — an intake-seeded PRD has no placeholders left for the scan
 * to count, so a render-only dismiss would come back on every reload.
 */
export default function OnboardingCard({ onStart }: { onStart: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  const { data } = useApiGet<OnboardingStatus>(
    ['onboarding-status'],
    '/api/cognition/onboarding-status',
    undefined,
    { refetchIntervalMs: 30_000 },
  );

  if (!data || data.complete || dismissed) return null;

  const remaining = data.placeholders_remaining ?? 0;

  return (
    <div
      className="m-4 flex items-start gap-4 rounded-xl border border-[var(--cos-border)] bg-[var(--cos-raised)] p-4 shadow-sm"
      role="region"
      aria-label="Project onboarding"
    >
      <div className="mt-0.5 shrink-0 rounded-lg bg-[var(--cos-brand-tint)] p-2 text-[var(--cos-accent)]">
        <Rocket size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-semibold text-[var(--cos-text)]">Set up your project</h3>
        <p className="mt-1 text-[12px] text-[var(--cos-muted)]" dir="auto">
          {remaining > 0
            ? `Your product docs are still placeholders (${remaining} to fill).`
            : 'Your product docs are only a one-line intake so far.'}{' '}
          A short guided interview drafts the essentials so the agent has real context to work
          from.
        </p>
        <button
          type="button"
          onClick={onStart}
          className="mt-3 rounded bg-[var(--cos-accent)] px-4 py-1.5 text-[11px] font-bold tracking-wide text-white uppercase focus-visible:ring-2 focus-visible:ring-white/40"
        >
          Set up your docs
        </button>
      </div>
      <button
        type="button"
        onClick={() => {
          setDismissed(true);
          void apiPost('/api/cognition/onboarding-status/dismiss', {}).catch(() => {});
        }}
        aria-label="Dismiss onboarding"
        className="shrink-0 rounded p-1 text-[var(--cos-faint)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      >
        <X size={16} />
      </button>
    </div>
  );
}
