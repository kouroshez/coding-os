import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./roles', () => ({ useRoles: (): string[] => [] }));
// ModelPicker (rendered by the composer) reads useApiGet — stub it so the test
// needs no QueryClientProvider; an empty adapter list is fine for the handoff test.
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: { adapters: [], default_model: '', count: 0 }, isLoading: false, error: null }),
}));

import NewChatForm from './NewChatForm';

function streamingFetch(frames: string[]) {
  const enc = new TextEncoder();
  let i = 0;
  return vi.fn(async () => ({
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          i < frames.length
            ? { value: enc.encode(frames[i++]), done: false }
            : { value: undefined, done: true },
      }),
    },
    text: async () => '',
  }));
}

describe('NewChatForm in-place handoff', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it('hands off with the SDK session id once the first turn finishes streaming', async () => {
    globalThis.fetch = streamingFetch([
      'event: session\ndata: {"session_id":"real-id-123"}\n\n',
      'event: done\ndata: {"session_id":"real-id-123"}\n\n',
    ]) as unknown as typeof fetch;

    const onComplete = vi.fn();
    render(<NewChatForm onComplete={onComplete} />);

    fireEvent.change(screen.getByPlaceholderText(/describe a task/i), { target: { value: 'hi' } });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith('real-id-123'));
  });
});
