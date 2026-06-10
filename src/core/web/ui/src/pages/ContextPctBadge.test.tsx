import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContextPctBadge } from './DashboardPage';

describe('ContextPctBadge', () => {
  it('renders an explicit unknown state, never a fabricated 0%', () => {
    render(<ContextPctBadge row={{ agent: 'claude', context_pct: null }} />);
    expect(screen.getByText('ctx ?')).toBeTruthy();
    expect(screen.queryByText(/0%/)).toBeNull();
  });

  it('renders the rounded percent with token detail in the title', () => {
    render(
      <ContextPctBadge
        row={{
          agent: 'claude',
          context_pct: 42.4,
          used_tokens: 84_800,
          context_window: 200_000,
        }}
      />,
    );
    const badge = screen.getByText('ctx 42%');
    expect(badge.getAttribute('title')).toContain('84,800');
  });
});
