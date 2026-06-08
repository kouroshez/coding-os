import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// Mock the data layer so we can feed a producer-shaped trace payload and
// assert the timeline reads it the way thinking_os/tracing.py emits it.
const hoisted = vi.hoisted(() => ({ payload: null as unknown }));
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: hoisted.payload, isLoading: false, error: null }),
}));

import TraceTimeline from './TraceTimeline';

function renderTrace(payload: unknown) {
  hoisted.payload = payload;
  return render(
    <MemoryRouter initialEntries={['/p/demo/cognition/sess-1']}>
      <TraceTimeline sessionId="sess-1" />
    </MemoryRouter>,
  );
}

describe('TraceTimeline producer contract', () => {
  it('reads summary + formula_id from e.data, not the (never-emitted) top level', () => {
    renderTrace({
      session_id: 'sess-1',
      events: [
        {
          kind: 'compose_done',
          ts: 1780000000,
          data: { summary: 'Chose researcher then reviewer', formula_id: 'audit_exhaustive' },
        },
      ],
      count: 1,
    });
    expect(screen.getByText('Chose researcher then reviewer')).toBeInTheDocument();
    expect(screen.getByText('audit_exhaustive')).toBeInTheDocument();
    expect(screen.queryByText('no further detail recorded')).toBeNull();
  });

  it('renders a clock time from e.ts (e.timestamp is never emitted)', () => {
    const { container } = renderTrace({
      session_id: 'sess-1',
      events: [{ kind: 'classify', ts: 1780000000 }],
      count: 1,
    });
    expect(container.textContent).toContain(new Date(1780000000 * 1000).toLocaleTimeString());
  });

  it('links "see chat" to the SDK uuid, not the trace session id', () => {
    renderTrace({
      session_id: 'ses-claude-20260101-aaaa',
      events: [{ kind: 'classify', ts: 1 }],
      count: 1,
      session: { sdk_uuid: 'sdk-xyz-uuid' },
    });
    const link = screen.getByRole('link', { name: /see chat/i });
    expect(link.getAttribute('href')).toContain('sdk-xyz-uuid');
    expect(link.getAttribute('href')).not.toContain('ses-claude-20260101-aaaa');
  });

  it('hides "see chat" when the session has no linked SDK transcript', () => {
    renderTrace({
      session_id: 'ses-only',
      events: [{ kind: 'classify', ts: 1 }],
      count: 1,
      session: { sdk_uuid: null },
    });
    expect(screen.queryByRole('link', { name: /see chat/i })).toBeNull();
  });
});
