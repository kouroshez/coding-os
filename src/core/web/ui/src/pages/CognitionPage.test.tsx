import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// The trace panes fetch on mount; stub the data layer so the redirect path
// renders without network.
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: null, isLoading: false, error: null }),
}));

import CognitionPage from './CognitionPage';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}</div>;
}

describe('CognitionPage', () => {
  it('redirects a legacy ?view=chat deep-link to the Workspace chat landing', () => {
    render(
      <MemoryRouter initialEntries={['/p/demo/cognition/abc-123?view=chat']}>
        <Routes>
          <Route path="/p/:slug/cognition/:sessionId" element={<CognitionPage />} />
          <Route path="/p/:slug/workspace/chat/:sessionId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('loc').textContent).toBe('/p/demo/workspace/chat/abc-123');
  });
});
