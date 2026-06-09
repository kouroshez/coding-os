import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

describe('ChatView — session-not-found grace', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows "syncing…" (not a hard error) on a fresh 404 and keeps polling', () => {
    mockResult = {
      data: undefined,
      isLoading: false,
      error: { status: 404, message: 'not found' },
      refetch: () => Promise.resolve(null),
    };
    render(<ChatView sessionId="brand-new-id" />);
    expect(screen.getByText(/syncing this session/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('surfaces a hard error for a non-404 failure', () => {
    mockResult = {
      data: undefined,
      isLoading: false,
      error: { status: 500, message: 'boom' },
      refetch: () => Promise.resolve(null),
    };
    render(<ChatView sessionId="x" />);
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
  });
});
