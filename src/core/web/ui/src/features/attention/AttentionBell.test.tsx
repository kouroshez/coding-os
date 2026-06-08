import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const hoisted = vi.hoisted(() => ({
  handler: null as null | ((t: string, d: unknown) => void),
}));
vi.mock('@/lib/use-event-stream', () => ({
  useEventStream: (_types: readonly string[], onEvent: (t: string, d: unknown) => void) => {
    hoisted.handler = onEvent;
    return 'live';
  },
}));

import AttentionBell from './AttentionBell';

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

afterEach(() => setHidden(false));

describe('AttentionBell (TASK-252)', () => {
  it('badges unread + tab title when an event arrives while the tab is hidden', () => {
    setHidden(true);
    render(<AttentionBell />);
    act(() => {
      hoisted.handler?.('dispatch-completed', { formula_id: 'reviewer', status: 'ok' });
    });
    expect(screen.getByLabelText(/activity, 1 new/i)).toBeInTheDocument();
    expect(document.title.startsWith('(1)')).toBe(true);
  });

  it('does not badge when the tab is focused (human is looking)', () => {
    setHidden(false);
    render(<AttentionBell />);
    act(() => {
      hoisted.handler?.('dispatch-completed', { formula_id: 'impl', status: 'ok' });
    });
    expect(screen.getByLabelText(/^activity$/i)).toBeInTheDocument();
  });

  it('opening the bell shows the activity feed item', () => {
    setHidden(false);
    render(<AttentionBell />);
    act(() => {
      hoisted.handler?.('agent-blocked', { reason: 'no doc anchor' });
    });
    act(() => {
      screen.getByLabelText(/activity/i).click();
    });
    expect(screen.getByText(/agent blocked: no doc anchor/i)).toBeInTheDocument();
  });
});
