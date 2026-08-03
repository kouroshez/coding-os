import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import DiagnosticsPage from './DiagnosticsPage';

describe('DiagnosticsPage', () => {
  it('leads with the Doctor tab and hosts no Overview (moved to Workspace, TASK-868)', () => {
    render(
      <MemoryRouter initialEntries={['/diagnostics']}>
        <DiagnosticsPage />
      </MemoryRouter>,
    );
    const doctor = screen.getByRole('link', { name: /doctor/i });
    expect(doctor).toHaveAttribute('href', '/diagnostics/doctor');
    expect(screen.queryByRole('link', { name: /overview/i })).toBeNull();
  });

  it('lists exactly the four diagnostics tabs', () => {
    render(
      <MemoryRouter initialEntries={['/p/demo/diagnostics']}>
        <DiagnosticsPage />
      </MemoryRouter>,
    );
    const names = screen.getAllByRole('link').map((l) => l.textContent?.trim());
    expect(names).toEqual(['Doctor', 'Logs', 'Observability', 'Sessions']);
  });
});
