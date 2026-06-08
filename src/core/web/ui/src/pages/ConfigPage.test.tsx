import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/hooks', () => ({
  useApiGet: (_key: unknown, path: string) => {
    const map: Record<string, unknown> = {
      '/api/config/stacks': {
        available: [{ id: 'meta', label: 'Meta', category: 'meta', primary_skill: 'graph-explorer', installed: true }],
        installed: ['meta'],
      },
      '/api/config/skills': { skills: [{ name: 'clean-code', tier: 'universal', domain: ['all'], globs: '**/*' }] },
      '/api/config/mcp': { servers: [{ name: 'coding-os', command: 'cos', args: ['server-start'], managed: true }] },
      '/api/hooks/list': { hooks: [{ name: 'branch-guard', event: 'PreToolUse', category: 'safety', phase: '1' }] },
    };
    return { data: map[path] ?? null, isLoading: false, error: null };
  },
}));

import ConfigPage from './ConfigPage';

function renderConfig(initial = '/p/demo/config') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ConfigPage />
    </MemoryRouter>,
  );
}

describe('ConfigPage', () => {
  it('defaults to the Stacks tab and shows installed status', () => {
    renderConfig();
    expect(screen.getByRole('tab', { name: 'Stacks' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Meta')).toBeInTheDocument();
    expect(screen.getByText('Installed')).toBeInTheDocument();
  });

  it('switches to the Skills tab on click', () => {
    renderConfig();
    fireEvent.click(screen.getByRole('tab', { name: 'Skills' }));
    expect(screen.getByText('clean-code')).toBeInTheDocument();
  });

  it('opens directly to the Hooks tab from ?tab=hooks', () => {
    renderConfig('/p/demo/config?tab=hooks');
    expect(screen.getByText('branch-guard')).toBeInTheDocument();
  });
});
