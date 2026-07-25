import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api-client';
import { SuggestNextButton } from './TopBar';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...mod, apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn() };
});

const mockedApiGet = vi.mocked(apiGet);

const card = {
  id: 'TASK-101',
  title: 'Wire the widget',
  swimlane: 'core',
  kind: 'feature',
  epic: null,
  labels: ['ready'],
  status: 'icebox',
  priority: 'P1',
};

describe('SuggestNextButton', () => {
  it('renders candidates from /api/board/pick and opens the drawer on click', async () => {
    mockedApiGet.mockResolvedValueOnce([{ candidates: [card], count: 1 }, null]);
    const onOpenTask = vi.fn();
    render(<SuggestNextButton onOpenTask={onOpenTask} />);

    fireEvent.click(screen.getByRole('button', { name: /suggest next/i }));
    await waitFor(() => expect(screen.getByText('TASK-101')).toBeTruthy());
    expect(mockedApiGet).toHaveBeenCalledWith('/api/board/pick', { max_candidates: 5 });

    fireEvent.click(screen.getByRole('option'));
    expect(onOpenTask).toHaveBeenCalledWith(card);
  });

  it('states the empty queue explicitly — never a silent blank panel', async () => {
    mockedApiGet.mockResolvedValueOnce([{ candidates: [], count: 0 }, null]);
    render(<SuggestNextButton onOpenTask={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /suggest next/i }));
    await waitFor(() => expect(screen.getByText(/no pullable task/i)).toBeTruthy());
  });

  it('surfaces fetch errors visibly', async () => {
    mockedApiGet.mockRejectedValueOnce(new Error('pick exploded'));
    render(<SuggestNextButton onOpenTask={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /suggest next/i }));
    await waitFor(() => expect(screen.getByText(/pick exploded/i)).toBeTruthy());
  });
});
