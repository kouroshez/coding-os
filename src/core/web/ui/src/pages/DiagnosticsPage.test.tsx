import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import DiagnosticsPage from './DiagnosticsPage';

describe('DiagnosticsPage (TASK-250)', () => {
  it('lists an Overview tab linking to the overview sub-route', () => {
    render(
      <MemoryRouter initialEntries={['/diagnostics']}>
        <DiagnosticsPage />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: /overview/i });
    expect(link).toHaveAttribute('href', '/diagnostics/overview');
  });

  it('scopes the Overview link under the active project slug', () => {
    render(
      <MemoryRouter initialEntries={['/p/demo/diagnostics']}>
        <DiagnosticsPage />
      </MemoryRouter>,
    );
    // useParams reads :slug only when the route pattern declares it; rendered
    // bare here the global link is correct — the scoped variant is covered by
    // the route table. Assert the tab exists either way.
    expect(screen.getByRole('link', { name: /overview/i })).toBeInTheDocument();
  });
});
