import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useEventStream } from './use-event-stream';

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: MockEventSource[] = [];

  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  private listeners: Record<string, Array<(e: unknown) => void>> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: (e: unknown) => void) {
    (this.listeners[type] ??= []).push(fn);
  }

  removeEventListener(type: string, fn: (e: unknown) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn);
  }

  close() {
    this.readyState = 2;
  }

  // --- test driver helpers ---
  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emit(type: string, data?: unknown) {
    const payload = data === undefined ? undefined : JSON.stringify(data);
    (this.listeners[type] ?? []).forEach((f) => f({ data: payload }));
  }

  fail(closed: boolean) {
    this.readyState = closed ? 2 : 0;
    (this.listeners.error ?? []).forEach((f) => f({}));
  }
}

function Probe({ onEvent }: { onEvent: (t: string, d: unknown) => void }) {
  const status = useEventStream(['presence-updated'], onEvent);
  return <span data-testid="status">{status}</span>;
}

function renderProbe(onEvent: (t: string, d: unknown) => void) {
  render(
    <MemoryRouter initialEntries={['/p/demo/workspace/chat']}>
      <Probe onEvent={onEvent} />
    </MemoryRouter>,
  );
  return MockEventSource.instances[0];
}

describe('useEventStream', () => {
  let original: typeof globalThis.EventSource;

  beforeEach(() => {
    original = globalThis.EventSource;
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  afterEach(() => {
    globalThis.EventSource = original;
  });

  it('goes live on open and delivers parsed events', () => {
    const onEvent = vi.fn();
    const es = renderProbe(onEvent);
    expect(screen.getByTestId('status').textContent).toBe('connecting');

    act(() => es.open());
    expect(screen.getByTestId('status').textContent).toBe('live');

    act(() => es.emit('presence-updated', { agent: 'claude' }));
    expect(onEvent).toHaveBeenCalledWith('presence-updated', { agent: 'claude' });
  });

  it('distinguishes reconnecting from closed via readyState', () => {
    const es = renderProbe(vi.fn());
    act(() => es.open());

    act(() => es.fail(false));
    expect(screen.getByTestId('status').textContent).toBe('reconnecting');

    act(() => es.fail(true));
    expect(screen.getByTestId('status').textContent).toBe('closed');
  });
});
