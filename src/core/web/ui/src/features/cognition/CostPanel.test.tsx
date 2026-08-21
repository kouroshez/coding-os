import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const responses: Record<string, unknown> = {};
vi.mock('@/lib/hooks', () => ({
  useApiGet: (key: string[]) => ({ data: responses[key[0]] }),
}));

import CostPanel from './CostPanel';

function setCost(byAdapter: unknown[], authMode = 'subscription') {
  responses['cognition-cost'] = {
    rows: [],
    by_adapter: byAdapter,
    auth_mode: authMode,
    total_usd: 1.13,
    count: 0,
  };
  responses['cognition-dispatchers'] = { dispatches: [], count: 0 };
}

describe('CostPanel', () => {
  it('shows an unpriced adapter as unknown, never as zero', () => {
    // The codex rows carry token counts and no USD figure. Rendering that as
    // $0.0000 reported 13 real dispatches as free.
    setCost([
      { adapter: 'codex', total_cost_usd: null, count: 13, avg_latency_ms: 1, auth_mode: 'subscription' },
    ]);
    render(<CostPanel onPick={() => {}} />);
    expect(screen.getByText('unpriced')).toBeInTheDocument();
    expect(screen.queryByText('0.0000$')).not.toBeInTheDocument();
  });

  it('still renders a real figure as money', () => {
    setCost([
      { adapter: 'claude', total_cost_usd: 1.1294, count: 3, avg_latency_ms: 1, auth_mode: 'api_key' },
    ]);
    render(<CostPanel onPick={() => {}} />);
    expect(screen.getByText('1.1294$')).toBeInTheDocument();
  });

  it('labels the total notional under a subscription', () => {
    setCost([], 'subscription');
    render(<CostPanel onPick={() => {}} />);
    expect(screen.getByText(/notional \(subscription — not billed\)/)).toBeInTheDocument();
  });

  it('leaves the total unqualified on an API key, where it is real spend', () => {
    setCost([], 'api_key');
    render(<CostPanel onPick={() => {}} />);
    expect(screen.queryByText(/notional/)).not.toBeInTheDocument();
  });
});
