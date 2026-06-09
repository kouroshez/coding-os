import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Drives useChatStatusLabel off a mocked /api/config/adapters payload so the
// data-driven status (adapter.yaml::chat_status) is guarded without a server.
let mockData: unknown = {
  adapters: [
    {
      id: 'claude',
      available: true,
      models: [{ id: 'claude-opus-4-8' }],
      chat_status: { tool_labels: { Read: 'Reading' }, idle_phrases: ['working'] },
    },
  ],
};
vi.mock('@/lib/hooks', () => ({ useApiGet: () => ({ data: mockData }) }));

import { useChatStatusLabel } from './chat-status';

describe('useChatStatusLabel', () => {
  it('maps a tool name to the adapter friendly verb', () => {
    const { result } = renderHook(() => useChatStatusLabel('claude-opus-4-8', 'Read', true));
    expect(result.current).toBe('Reading');
  });

  it('strips an mcp prefix and falls back to the cleaned tool name', () => {
    const { result } = renderHook(() =>
      useChatStatusLabel('', 'mcp__coding-os__cos_graph_query', true),
    );
    expect(result.current).toBe('cos_graph_query');
  });

  it('uses a playful idle phrase when no tool is active', () => {
    const { result } = renderHook(() => useChatStatusLabel('', '', false));
    expect(result.current).toBe('working');
  });

  it('falls back to "working" when the adapter declares no chat_status', () => {
    mockData = { adapters: [{ id: 'x', available: true, models: [{ id: 'm' }] }] };
    const { result } = renderHook(() => useChatStatusLabel('m', '', false));
    expect(result.current).toBe('working');
  });
});
