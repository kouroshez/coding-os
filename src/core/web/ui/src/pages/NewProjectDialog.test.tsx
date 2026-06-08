import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({
    data: { stacks: [{ id: 'python', label: 'Python', category: 'backend' }], count: 1 },
    isLoading: false,
    error: null,
  }),
  invalidateApiQueries: vi.fn(),
}));

import { NewProjectDialog, slugifyProjectName } from './HubHome';

describe('slugifyProjectName (TASK-249)', () => {
  it('lowercases + dashes unsafe chars', () => {
    expect(slugifyProjectName('My App!')).toBe('my-app');
    expect(slugifyProjectName('  Cool_Thing 2  ')).toBe('cool_thing-2');
  });
  it('trims leading/trailing separators', () => {
    expect(slugifyProjectName('--edge--')).toBe('edge');
  });
});

describe('NewProjectDialog (TASK-249)', () => {
  it('previews the slug and submits name+parent+stack', () => {
    const onSubmit = vi.fn();
    render(
      <NewProjectDialog
        suggestions={['/Users/me/code']}
        onCancel={() => {}}
        onSubmit={onSubmit}
        busy={false}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText('my-app'), { target: { value: 'My App' } });
    expect(screen.getByText('my-app')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Python' }));
    fireEvent.click(screen.getByRole('button', { name: /create project/i }));
    expect(onSubmit).toHaveBeenCalledWith('my-app', '/Users/me/code', 'python');
  });

  it('disables create until a valid name is entered', () => {
    render(
      <NewProjectDialog suggestions={['/code']} onCancel={() => {}} onSubmit={vi.fn()} busy={false} />,
    );
    expect(screen.getByRole('button', { name: /create project/i })).toBeDisabled();
  });
});
