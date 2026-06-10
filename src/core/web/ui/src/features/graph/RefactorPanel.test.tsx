import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api-client';
import { RenamePlanSection } from './RefactorPanel';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...mod, apiGet: vi.fn() };
});

const mockedApiGet = vi.mocked(apiGet);

const plan = {
  old_name: 'safe_tool',
  new_name: 'safe_tool_v2',
  uid: 'code:function:x.py::safe_tool',
  call_sites: [{ source_uid: 'code:function:a.py::caller', target_uid: 'x' }],
  call_sites_total_count: 42,
  doc_references: [],
  doc_references_total_count: 0,
  test_references: [],
  test_references_total_count: 0,
  string_literals: [{ file: 'docs/x.md', line: 7, text: 'safe_tool' }],
  risk: 'high',
  suggested_order: 'tests first',
  confidence: 0.9,
};

describe('RenamePlanSection', () => {
  it('fetches the plan and surfaces truncation instead of hiding it', async () => {
    mockedApiGet.mockResolvedValueOnce([plan, null]);
    render(<RenamePlanSection uid={plan.uid} />);

    fireEvent.change(screen.getByLabelText(/new symbol name/i), {
      target: { value: 'safe_tool_v2' },
    });
    fireEvent.click(screen.getByRole('button', { name: /plan rename/i }));

    await waitFor(() => expect(screen.getByText(/call sites · 42/i)).toBeTruthy());
    expect(mockedApiGet).toHaveBeenCalledWith(
      `/api/graph/rename-plan/${encodeURIComponent(plan.uid)}`,
      { new_name: 'safe_tool_v2' },
    );
    // 1 shown of 42 total → the truncation badge must be visible.
    expect(screen.getByText(/showing 1 — truncated/i)).toBeTruthy();
    expect(screen.getByText('docs/x.md:7')).toBeTruthy();
  });

  it('renders resolver errors visibly', async () => {
    mockedApiGet.mockRejectedValueOnce(new Error('uid not found'));
    render(<RenamePlanSection uid="code:function:gone.py::x" />);

    fireEvent.change(screen.getByLabelText(/new symbol name/i), { target: { value: 'y' } });
    fireEvent.click(screen.getByRole('button', { name: /plan rename/i }));

    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/uid not found/i));
  });
});
