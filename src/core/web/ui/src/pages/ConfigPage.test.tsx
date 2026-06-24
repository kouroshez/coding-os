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
      '/api/settings/modules': {
        modules: [
          { id: 'kernel', label: 'Kernel', kernel: true, enabled: true, depends_on: [], hooks: 6, tools: 0 },
          { id: 'tasks', label: 'Task system', kernel: false, enabled: true, depends_on: ['docs'], hooks: 9, tools: 2 },
        ],
      },
      '/api/settings': {
        settings: {
          git_settings: {
            enabled: false,
            integration_branch: 'main',
            protected_branches: ['production'],
            autonomy_level: 'draft',
          },
        },
      },
      '/api/settings/git-state': {
        remote: false,
        gh: false,
        required_check: false,
        pr_ok: false,
        missing: [],
        branches: [],
        current_branch: 'main',
        remote_url: '',
      },
    };
    return { data: map[path] ?? null, isLoading: false, error: null };
  },
  invalidateApiQueries: vi.fn(),
}));

const apiPatch = vi.fn().mockResolvedValue([{}]);
vi.mock('@/lib/api-client', () => ({
  apiPatch: (...args: unknown[]) => apiPatch(...args),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({}),
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


describe('ModulesTab (TASK-354)', () => {
  it('kernel renders locked without a toggle; non-kernel toggles via PATCH', async () => {
    renderConfig('/p/demo/config?tab=modules');
    expect(screen.getByText('kernel · locked')).toBeInTheDocument();
    expect(screen.queryByTestId('module-toggle-kernel')).toBeNull();
    const toggle = screen.getByTestId('module-toggle-tasks');
    fireEvent.click(toggle);
    expect(apiPatch).toHaveBeenCalledWith('/api/settings/modules/tasks', { enabled: false });
  });
});

describe('GitTab (TASK-552)', () => {
  it('renders the full editable tab plus a trunk caution for the meta-repo (slug coding-os)', () => {
    renderConfig('/p/coding-os/config?tab=git');
    // The configurator is NOT hidden on coding-os anymore — the full tab renders.
    expect(screen.getByRole('checkbox', { name: 'Enable pr-mode' })).toBeInTheDocument();
    expect(screen.getByText('Team + GitHub CI')).toBeInTheDocument();
    // ...with one caution that enabling here flips the mother repo off trunk.
    expect(screen.getByText(/viewing coding-os, the meta-repo/)).toBeInTheDocument();
    // The old read-only dead-box banner is gone.
    expect(screen.queryByText('coding-os itself stays trunk.')).toBeNull();
  });

  it('offers quick-start presets and per-field info controls on a consumer project', () => {
    renderConfig('/p/demo/config?tab=git');
    expect(screen.getByRole('checkbox', { name: 'Enable pr-mode' })).toBeInTheDocument();
    expect(screen.getByText('Team + GitHub CI')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is Integration branch?' })).toBeInTheDocument();
  });

  it('the None control clears protected branches and reads "None"', () => {
    renderConfig('/p/demo/config?tab=git');
    expect(screen.getByText('Human-only: production')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'None' }));
    expect(screen.getByText('None — no protected branches.')).toBeInTheDocument();
  });

  it('Save sends the unchanged PATCH payload shape', () => {
    renderConfig('/p/demo/config?tab=git');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(apiPatch).toHaveBeenCalledWith('/api/settings', {
      git_settings: {
        enabled: false,
        integration_branch: 'main',
        protected_branches: ['production'],
        autonomy_level: 'draft',
      },
    });
  });
});
