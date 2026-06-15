import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Composer tests — TASK-419 (single-screen new-project flow).
 * Replaces the step-wizard tests (TASK-358); the flow is now one screen
 * with a live preview + an Advanced section (agents multi-select, skills).
 */

const FIXTURES: Record<string, unknown> = {
  '/api/hub/presets': {
    presets: [
      {
        id: 'nextjs-fastapi',
        label: 'Next.js + FastAPI full-stack',
        description: 'TS frontend + Python API',
        stacks: ['nextjs', 'fastapi'],
      },
    ],
  },
  '/api/hub/stacks': {
    stacks: [
      { id: 'fastapi', label: 'FastAPI', category: 'backend', language: 'python' },
      { id: 'go-fiber', label: 'Go Fiber', category: 'backend', language: 'go' },
      { id: 'nextjs', label: 'Next.js', category: 'frontend', language: 'typescript' },
    ],
  },
  '/api/hub/adapters': {
    adapters: [
      { id: 'claude', label: 'Claude Code' },
      { id: 'codex', label: 'Codex CLI' },
    ],
  },
  '/api/hub/skills': { skills: [] },
};

vi.mock('@/lib/hooks', () => ({
  useApiGet: (_key: unknown, path: string) => ({
    data: FIXTURES[path],
    isLoading: false,
    error: null,
  }),
  invalidateApiQueries: vi.fn(),
}));

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('@/lib/api-client', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
}));

import OnboardingWizard from './OnboardingWizard';
import { slugifyProjectName } from './HubHome';

const VALIDATE_OK = {
  valid: true,
  name: 'proj-abc123',
  auto_named: true,
  target: '/code/proj-abc123',
  templates: ['nextjs', 'fastapi'],
  agents: ['claude'],
  swimlanes: ['backend', 'frontend', 'docs'],
  conflicts: [],
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};

  url: string;

  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(handler);
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners[type] ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  close() {}
}

beforeEach(() => {
  apiGet.mockReset().mockResolvedValue([
    { stack: 'fastapi', groups: { required: [], recommended: [], optional: [] } },
  ]);
  apiPost.mockReset().mockImplementation(async (path: string) =>
    (String(path).endsWith('/init') ? [{ job_id: 'job-xyz', name: 'proj-abc123' }] : [VALIDATE_OK]));
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource);
});

function renderComposer(onCreated = vi.fn()) {
  render(
    <OnboardingWizard suggestions={['/code']} onClose={() => {}} onCreated={onCreated} />,
  );
  return onCreated;
}

const createBtn = () => screen.getByRole('button', { name: 'Create project' });

describe('slugifyProjectName (still exported from HubHome)', () => {
  it('lowercases + dashes unsafe chars', () => {
    expect(slugifyProjectName('My App!')).toBe('my-app');
  });
});

describe('Composer (TASK-419)', () => {
  it('keeps Create disabled until a preset is chosen, then enables it', async () => {
    renderComposer();
    expect(createBtn()).toBeDisabled();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    // live validate fires on a debounce; VALIDATE_OK has valid: true
    await waitFor(() => expect(createBtn()).toBeEnabled());
  });

  it('shows a live preview (swimlanes, agents) from validate-init', async () => {
    renderComposer();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/hub/registry/validate-init',
      expect.objectContaining({ preset: 'nextjs-fastapi', agents: ['claude'] }),
    ));
    // board lanes from the dry-run render as chips (no raw JSON)
    await waitFor(() => expect(screen.getByText('backend')).toBeInTheDocument());
    expect(screen.getByText('frontend')).toBeInTheDocument();
  });

  it('agents are multi-select in Advanced and ride the init payload', async () => {
    const onCreated = renderComposer();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    fireEvent.click(screen.getByRole('button', { name: /Advanced/ }));
    fireEvent.click(screen.getByTestId('agent-codex')); // add codex alongside claude
    await waitFor(() => expect(createBtn()).toBeEnabled());
    fireEvent.click(createBtn());

    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const initCall = apiPost.mock.calls.find(([p]) => String(p).endsWith('/registry/init'));
    expect(initCall?.[1]).toMatchObject({
      preset: 'nextjs-fastapi',
      stacks: [],
      agents: ['claude', 'codex'],
      background: true,
    });

    FakeEventSource.instances[0].emit('succeeded', { status: 'succeeded', result: { slug: 'proj-abc123' } });
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('proj-abc123'));
  });

  it('forwards the description and starts a job, reporting progress', async () => {
    renderComposer();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    fireEvent.change(screen.getByPlaceholderText(/booking app/i), {
      target: { value: 'A product for testing the composer.' },
    });
    await waitFor(() => expect(createBtn()).toBeEnabled());
    fireEvent.click(createBtn());

    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const stream = FakeEventSource.instances[0];
    expect(stream.url).toContain('/api/hub/init-jobs/job-xyz/events');
    stream.emit('log', { line: 'Installing claude adapter...' });
    stream.emit('phase', { phase: 'docs-seed' });
    await waitFor(() =>
      expect(screen.getByTestId('job-log')).toHaveTextContent('Installing claude adapter'));
    expect(screen.getByText('Agent is processing your description & docs')).toBeInTheDocument();

    const initCall = apiPost.mock.calls.find(([p]) => String(p).endsWith('/registry/init'));
    expect(initCall?.[1]).toMatchObject({
      description: 'A product for testing the composer.',
      background: true,
    });
  });

  it('cancel during a running job returns the UI to an actionable state', async () => {
    renderComposer();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    await waitFor(() => expect(createBtn()).toBeEnabled());
    fireEvent.click(createBtn());
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    const cancelCall = apiPost.mock.calls.find(([p]) => String(p).includes('/cancel'));
    expect(cancelCall?.[0]).toContain('/api/hub/init-jobs/job-xyz/cancel');

    FakeEventSource.instances[0].emit('cancelled', {
      status: 'cancelled', cleanup: { removed_dir: '/code/proj-abc123' },
    });
    await waitFor(() =>
      expect(screen.getByText(/partial scaffold was removed/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Back to composer/ }));
    await waitFor(() => expect(createBtn()).toBeInTheDocument());
  });

  it('surfaces the dry-run validation error inline', async () => {
    apiPost.mockReset().mockImplementation(async (path: string) => {
      if (String(path).endsWith('/validate-init')) throw new Error('parent_dir is not writable: /code');
      return [{ job_id: 'x', name: 'y' }];
    });
    renderComposer();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('not writable'));
    expect(createBtn()).toBeDisabled();
  });
});

describe('Composer support-link isolation (TASK-372)', () => {
  it('never renders Hub support / community links inside the composer', () => {
    render(<OnboardingWizard suggestions={['/code']} onClose={() => {}} onCreated={vi.fn()} />);
    expect(screen.queryByRole('link', { name: /sponsor/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /coffee/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /crypto/i })).toBeNull();
  });
});
