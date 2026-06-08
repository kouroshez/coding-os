import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const hoisted = vi.hoisted(() => ({ agents: [] as unknown[] }));
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: { agents: hoisted.agents }, isLoading: false, error: null }),
}));

import LiveAgentsPanel from './LiveAgentsPanel';

// jsdom has no EventSource; useEventStream only needs the constructor + the
// listener/close surface here (no events are driven in these tests).
class StubEventSource {
  static CLOSED = 2;
  readyState = 0;
  onopen: (() => void) | null = null;
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/']}>
        <LiveAgentsPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LiveAgentsPanel', () => {
  let original: typeof globalThis.EventSource;
  beforeEach(() => {
    original = globalThis.EventSource;
    globalThis.EventSource = StubEventSource as unknown as typeof EventSource;
  });
  afterEach(() => {
    globalThis.EventSource = original;
  });

  it('renders one humanized card per non-offline agent', () => {
    hoisted.agents = [
      { agent: 'claude', state: 'active', model: 'claude-opus-4-8[1m]', gate: 'COMPLEX 6', role: 'researcher' },
      { agent: 'codex', state: 'offline', model: null },
    ];
    renderPanel();
    expect(screen.getByText('claude')).toBeInTheDocument();
    expect(screen.getByText('Opus 4.8 · 1M')).toBeInTheDocument();
    expect(screen.queryByText('codex')).toBeNull(); // offline is filtered out
  });

  it('opens the detail modal on card click instead of navigating away', () => {
    hoisted.agents = [
      {
        agent: 'claude',
        state: 'active',
        model: 'claude-opus-4-8[1m]',
        gate: 'COMPLEX 6',
        role: 'researcher',
        session_id: 'ses-1',
        task: 'TASK-9',
      },
    ];
    renderPanel();
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /open details for claude/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Thinking depth')).toBeInTheDocument();
    expect(screen.getByText('Current task')).toBeInTheDocument();
  });
});
