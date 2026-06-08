import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const hoisted = vi.hoisted(() => ({ error: null as unknown }));
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: null, error: hoisted.error, isLoading: false }),
}));

import ChatLanding from './ChatLanding';

describe('ChatLanding', () => {
  it('degrades to install guidance when the Claude SDK is unavailable', () => {
    hoisted.error = { category: 'unavailable', message: 'claude_agent_sdk not installed' };
    render(
      <MemoryRouter initialEntries={['/p/demo/workspace/chat']}>
        <ChatLanding />
      </MemoryRouter>,
    );
    expect(screen.getByText(/chat needs claude code/i)).toBeInTheDocument();
    // the sidebar must NOT render in the unavailable state (no raw error)
    expect(screen.queryByLabelText(/chat sessions/i)).toBeNull();
  });
});
