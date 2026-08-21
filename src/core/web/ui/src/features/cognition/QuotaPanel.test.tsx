import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

let mockData: unknown;
vi.mock('@/lib/hooks', () => ({ useApiGet: () => ({ data: mockData }) }));

import QuotaPanel, { humanizeAge, humanizeReset } from './QuotaPanel';

const claude = {
  adapter: 'claude',
  status: 'ok',
  reason: '',
  auth_mode: 'subscription',
  plan: 'claude_max (default_claude_max_20x)',
  source: '~/.claude.json :: cachedUsageUtilization',
  observed_at: '2026-08-20T18:48:45+00:00',
  age_seconds: 120,
  stale: false,
  windows: [
    {
      label: '5h',
      percent: 0,
      resets_at: null,
      severity: 'normal',
      window_minutes: 300,
      scope: null,
    },
    {
      label: 'weekly · Fable',
      percent: 78,
      resets_at: null,
      severity: 'warning',
      window_minutes: 10080,
      scope: 'Fable',
    },
  ],
};

describe('QuotaPanel', () => {
  it('renders every window the provider reports, scoped ones included', () => {
    // The binding limit on a real account was the per-model weekly cap while
    // the headline windows read 0% — showing only the headlines hides it.
    mockData = { adapters: [claude], tightest: null, checked_at: '' };
    render(<QuotaPanel />);
    expect(screen.getByRole('meter', { name: 'claude 5h used' })).toBeInTheDocument();
    const scoped = screen.getByRole('meter', { name: 'claude weekly · Fable used' });
    expect(scoped).toHaveAttribute('aria-valuenow', '78');
  });

  it('shows the reading age even when it is fresh', () => {
    // A percentage with no timestamp invites the reader to assume it is live.
    mockData = { adapters: [claude], tightest: null, checked_at: '' };
    render(<QuotaPanel />);
    expect(screen.getByText(/2m ago/)).toBeInTheDocument();
    expect(screen.queryByText(/stale/)).not.toBeInTheDocument();
  });

  it('marks a stale reading', () => {
    mockData = {
      adapters: [{ ...claude, age_seconds: 35248, stale: true }],
      tightest: null,
      checked_at: '',
    };
    render(<QuotaPanel />);
    expect(screen.getByText(/10h ago · stale/)).toBeInTheDocument();
  });

  it('reports why an adapter has nothing rather than drawing an empty bar', () => {
    mockData = {
      adapters: [
        {
          ...claude,
          adapter: 'codex',
          status: 'unavailable',
          reason: 'no session rollouts under ~/.codex/sessions',
          windows: [],
        },
      ],
      tightest: null,
      checked_at: '',
    };
    render(<QuotaPanel />);
    expect(screen.getByText(/no session rollouts/)).toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });

  it('surfaces the tightest window across providers', () => {
    mockData = {
      adapters: [claude],
      tightest: { ...claude.windows[1], adapter: 'claude' },
      checked_at: '',
    };
    render(<QuotaPanel />);
    expect(screen.getByText(/tightest: claude weekly · Fable 78%/)).toBeInTheDocument();
  });

  it('says so when no adapter reports a window', () => {
    mockData = { adapters: [], tightest: null, checked_at: '' };
    render(<QuotaPanel />);
    expect(screen.getByText(/no adapter reports a quota window/)).toBeInTheDocument();
  });
});

describe('humanizeAge', () => {
  it('never renders an unknown age as fresh', () => {
    expect(humanizeAge(null)).toBe('unknown age');
  });

  it.each([
    [30, '30s ago'],
    [600, '10m ago'],
    [35248, '10h ago'],
    [320698, '4d ago'],
  ])('renders %i seconds as %s', (seconds, expected) => {
    expect(humanizeAge(seconds)).toBe(expected);
  });
});

describe('humanizeReset', () => {
  const now = Date.parse('2026-08-21T12:00:00Z');

  it('counts down to the reset', () => {
    expect(humanizeReset('2026-08-21T14:00:00Z', now)).toBe('resets in 2h');
  });

  it('does not render a negative countdown for a window already past', () => {
    expect(humanizeReset('2026-08-21T11:00:00Z', now)).toBe('resetting');
  });

  it('renders nothing when the provider gave no reset time', () => {
    expect(humanizeReset(null, now)).toBe('');
    expect(humanizeReset('not a date', now)).toBe('');
  });
});
