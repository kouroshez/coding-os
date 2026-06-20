import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { apiGet } from '@/lib/api-client';
import DiffTriagePanel from './DiffTriagePanel';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...mod, apiGet: vi.fn() };
});

const mockedApiGet = vi.mocked(apiGet);

beforeEach(() => {
  mockedApiGet.mockReset();
});

const payload = {
  scope: 'HEAD~1..HEAD',
  files: ['a.py'],
  symbols: [{ file: 'a.py', source: 'code:function:a.py::foo', target: 'x', edge_type: 'calls' }],
  downstream_consumers: [
    { file: 'a.py', consumer: 'code:function:b.py::bar', target: 'x', edge_type: 'calls', confidence: 0.9 },
  ],
  downstream_tasks: ['task:TASK-001'],
  risk_level: 'medium',
};

describe('DiffTriagePanel', () => {
  it('triages a range, renders the graph-diff fields, and surfaces truncation honestly', async () => {
    mockedApiGet.mockResolvedValueOnce([payload, { walk_truncated: true }]);
    render(<DiffTriagePanel />);

    fireEvent.click(screen.getByRole('button', { name: /triage diff/i }));

    await waitFor(() => expect(screen.getByText(/changed symbols · 1/i)).toBeTruthy());
    expect(screen.getByText(/downstream consumers · 1/i)).toBeTruthy();
    expect(screen.getByText(/downstream tasks · 1/i)).toBeTruthy();
    // risk_level is labelled heuristic, never an authoritative score.
    expect(screen.getByText(/heuristic/i)).toBeTruthy();
    // meta.walk_truncated is surfaced, not hidden.
    expect(screen.getByText(/visit cap/i)).toBeTruthy();
  });

  it('does not hit the API until a range is submitted (manual entry path)', () => {
    render(<DiffTriagePanel />);
    expect(mockedApiGet).not.toHaveBeenCalled();
    expect((screen.getByLabelText(/base ref/i) as HTMLInputElement).value).toBe('HEAD~1');
    expect((screen.getByLabelText(/head ref/i) as HTMLInputElement).value).toBe('HEAD');
  });
});
