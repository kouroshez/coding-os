import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// Guards the "session vanished" fix: a fresh 404 (the SDK jsonl not queryable
// yet) must show a quiet "syncing…" that keeps polling, NOT a hard error that
// replaces the conversation. A non-404 error is still surfaced.

let mockResult: {
  data?: unknown;
  isLoading: boolean;
  error: { status?: number; message?: string } | null;
  refetch: () => Promise<unknown>;
};
vi.mock('@/lib/hooks', () => ({ useApiGet: () => mockResult }));
vi.mock('@/lib/use-scoped-link', () => ({
  useScopedLink: () => ({ scopedLink: (a: string, b: string) => `/${a}/${b}` }),
}));

import ChatView from './ChatView';

function renderChat(sessionId: string) {
  return render(
    <MemoryRouter>
      <ChatView sessionId={sessionId} />
    </MemoryRouter>,
  );
}

describe('ChatView — transcript states', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('centers an accessible loading state', () => {
    mockResult = {
      data: undefined,
      isLoading: true,
      error: null,
      refetch: () => Promise.resolve(null),
    };
    renderChat('loading-id');
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Loading transcript');
    expect(status.parentElement).toHaveClass('items-center', 'justify-center');
  });

  it('shows "syncing…" (not a hard error) on a fresh 404 and keeps polling', () => {
    mockResult = {
      data: undefined,
      isLoading: false,
      error: { status: 404, message: 'not found' },
      refetch: () => Promise.resolve(null),
    };
    renderChat('brand-new-id');
    expect(screen.getByRole('status')).toHaveTextContent('Connecting to this session');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('turns a persistent 404 into a terminal state with a working retry', async () => {
    vi.useFakeTimers();
    const refetch = vi.fn(() => Promise.resolve(null));
    mockResult = {
      data: undefined,
      isLoading: false,
      error: { status: 404, message: 'not found' },
      refetch,
    };
    renderChat('missing-id');
    await act(async () => vi.advanceTimersByTime(12_000));
    expect(screen.getByRole('alert')).toHaveTextContent('This session is no longer available');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('surfaces a hard error for a non-404 failure', () => {
    mockResult = {
      data: undefined,
      isLoading: false,
      error: { status: 500, message: 'boom' },
      refetch: () => Promise.resolve(null),
    };
    renderChat('x');
    expect(screen.getByRole('alert')).toHaveTextContent('Transcript could not be loaded');
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
  });
});
