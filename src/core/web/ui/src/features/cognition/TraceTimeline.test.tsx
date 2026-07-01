import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// Mock the data layer so we can feed a producer-shaped trace payload and
// assert the timeline reads it the way thinking_os/tracing.py emits it.
const hoisted = vi.hoisted(() => ({
  payload: null as unknown,
  traceListeners: [] as Array<(ev: MessageEvent) => void>,
  errorListeners: [] as Array<(ev: MessageEvent) => void>,
}));
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: hoisted.payload, isLoading: false, error: null }),
}));
// Trace SSE tail (TASK-667): capture the `trace` listener so a test can push a
// live event, and keep jsdom (which ships no EventSource) from throwing.
vi.mock('@/lib/api-client', () => ({ resolveApiUrl: (p: string) => p }));
vi.mock('@/lib/shared-event-source', () => ({
  acquireEventSource: () => ({
    source: {
      readyState: 1,
      addEventListener: (type: string, cb: (ev: MessageEvent) => void) => {
        if (type === 'trace') hoisted.traceListeners.push(cb);
        if (type === 'error') hoisted.errorListeners.push(cb);
      },
      removeEventListener: () => {},
    },
    release: () => {},
  }),
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

  it('groups summary events into cognitive phases via e.node', () => {
    renderTrace({
      session_id: 'sess-1',
      events: [
        { kind: 'gate_recorded', node: 'n-gate', ts: 1, data: { summary: 'Sized the task' } },
        { kind: 'dispatch_completed', node: 'n-supervisor', ts: 2, data: { summary: 'Ran sub-agent' } },
      ],
      count: 2,
    });
    expect(screen.getByText('Setup')).toBeInTheDocument();
    expect(screen.getByText('Execute')).toBeInTheDocument();
    expect(screen.getByText('Sized the task')).toBeInTheDocument();
    expect(screen.getByText('Ran sub-agent')).toBeInTheDocument();
  });

  it('appends live trace events streamed over the SSE tail', () => {
    hoisted.traceListeners.length = 0;
    renderTrace({
      session_id: 'sess-1',
      events: [
        {
          kind: 'dispatch_started',
          node: 'n-supervisor',
          ts: 1,
          span_id: 'sp-0',
          data: { summary: 'Dispatch began' },
        },
      ],
      count: 1,
    });
    expect(screen.queryByText('Sub-agent finished live')).toBeNull();
    act(() => {
      for (const cb of hoisted.traceListeners) {
        cb({
          data: JSON.stringify({
            kind: 'dispatch_completed',
            node: 'n-supervisor',
            ts: 2,
            span_id: 'sp-live-1',
            data: { summary: 'Sub-agent finished live' },
          }),
        } as MessageEvent);
      }
    });
    expect(screen.getByText('Sub-agent finished live')).toBeInTheDocument();
    expect(screen.getByText('Dispatch began')).toBeInTheDocument();
  });

  it('surfaces a backend SSE error frame instead of silently freezing (review fix #6)', () => {
    hoisted.errorListeners.length = 0;
    renderTrace({
      session_id: 'sess-1',
      events: [{ kind: 'classify', ts: 1, span_id: 'sp-0' }],
      count: 1,
    });
    expect(screen.queryByText(/live tail interrupted/i)).toBeNull();
    act(() => {
      for (const cb of hoisted.errorListeners) {
        cb({ data: JSON.stringify({ message: 'trace stream failed' }) } as MessageEvent);
      }
    });
    expect(screen.getByText(/live tail interrupted: trace stream failed/i)).toBeInTheDocument();
    // Recovery: a trace event arriving after the error clears the stuck banner.
    act(() => {
      for (const cb of hoisted.traceListeners) {
        cb({ data: JSON.stringify({ kind: 'classify', ts: 2, span_id: 'sp-1' }) } as MessageEvent);
      }
    });
    expect(screen.queryByText(/live tail interrupted/i)).toBeNull();
  });
});
