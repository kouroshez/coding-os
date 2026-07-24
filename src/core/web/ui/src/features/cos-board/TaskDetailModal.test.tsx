import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Stub the API hooks so the modal renders from its `task` prop fallback with no
// network — these tests assert the a11y + stacking contract (TASK-260 / S12),
// not data fetching.
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: undefined, isLoading: false, error: null }),
  invalidateApiQueries: vi.fn(),
}));

import { TaskDetailDrawer } from './task-detail';
import type { BoardListCard } from './types';

const mockTask = {
  id: 'TASK-001',
  title: 'Sample task',
  swimlane: 'core',
  kind: 'feature',
  epic: null,
  labels: [],
  status: 'icebox',
  priority: 'P2',
  appetite: '1d',
} as unknown as BoardListCard;

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TaskDetailDrawer task={mockTask} swimlanes={[]} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('TaskDetailModal — modal hardening (TASK-260 / S12)', () => {
  it('renders an accessible centered dialog (role + aria-modal + centering)', () => {
    renderModal();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby');
    // Centered modal (TASK-172), not a right-edge drawer.
    expect(dialog.style.transform).toContain('translate(-50%, -50%)');
  });

  it('exposes an accessible Close control via aria-label', () => {
    renderModal();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('stacks the modal panel above toast/overlay layers (z-index >= 200, was 81)', () => {
    renderModal();
    const dialog = screen.getByRole('dialog');
    expect(Number(dialog.style.zIndex)).toBeGreaterThanOrEqual(200);
  });
});
