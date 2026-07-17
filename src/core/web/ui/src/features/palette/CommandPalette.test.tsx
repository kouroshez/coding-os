import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn((path: string) => {
    if (path === '/api/hub/projects')
      return Promise.resolve([{ projects: [{ slug: 'alpha', path: '/a' }] }, null]);
    if (path === '/api/board/list')
      return Promise.resolve([{ cards: [{ id: 'TASK-9', title: 'do X', status: 'wip' }] }, null]);
    if (path === '/api/cognition/chats')
      return Promise.resolve([{ sessions: [{ session_id: 'ses-1', summary: 'hello' }] }, null]);
    return Promise.resolve([{}, null]);
  }),
}));

import CommandPalette, { filterCommandItems, type CommandItem } from './CommandPalette';

const ITEMS: CommandItem[] = [
  { type: 'project', id: 'alpha', label: 'alpha', sub: '/a', target: '/p/alpha/workspace/chat' },
  { type: 'task', id: 'TASK-9', label: 'TASK-9 do X', sub: 'wip', target: '/board' },
];

describe('filterCommandItems (TASK-253)', () => {
  it('returns all on empty query', () => {
    expect(filterCommandItems(ITEMS, '')).toHaveLength(2);
  });
  it('matches label + sub case-insensitively', () => {
    expect(filterCommandItems(ITEMS, 'ALPHA')).toEqual([ITEMS[0]]);
    expect(filterCommandItems(ITEMS, 'task-9')).toEqual([ITEMS[1]]);
    expect(filterCommandItems(ITEMS, 'wip')).toEqual([ITEMS[1]]);
  });
});

describe('CommandPalette (TASK-253)', () => {
  it('opens on Cmd+K, lists sources, and navigates on Enter', async () => {
    navigateMock.mockClear();
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByLabelText(/command palette search/i);
    await screen.findByText('alpha');
    fireEvent.change(input, { target: { value: 'alpha' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/p/alpha/workspace/chat'),
    );
  });
});
