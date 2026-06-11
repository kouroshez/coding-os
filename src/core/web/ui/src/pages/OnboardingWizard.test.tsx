import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

import OnboardingWizard, { wizardSteps } from './OnboardingWizard';
import { slugifyProjectName } from './HubHome';

const VALIDATE_OK = {
  valid: true,
  name: 'proj-abc123',
  auto_named: true,
  target: '/code/proj-abc123',
  templates: ['nextjs', 'fastapi'],
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
  apiPost.mockReset().mockResolvedValue([VALIDATE_OK]);
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource);
});

describe('slugifyProjectName (kept after dialog→wizard migration)', () => {
  it('lowercases + dashes unsafe chars', () => {
    expect(slugifyProjectName('My App!')).toBe('my-app');
  });
});

describe('wizardSteps (TASK-358)', () => {
  it('preset mode skips the stack picker; custom includes it', () => {
    const base = {
      mode: null, preset: '', stacks: [] as string[], agent: 'claude',
      extraSkills: [] as string[], name: '', skipName: false, description: '', parentDir: '',
    };
    expect(wizardSteps({ ...base, mode: 'preset' })).not.toContain('stacks');
    expect(wizardSteps({ ...base, mode: 'custom' })).toContain('stacks');
    expect(wizardSteps({ ...base, mode: 'custom' })).toEqual([
      'mode', 'stacks', 'agent', 'skills', 'extra', 'swimlanes', 'name', 'description', 'review',
    ]);
  });
});

function renderWizard(onCreated = vi.fn()) {
  render(
    <OnboardingWizard suggestions={['/code']} onClose={() => {}} onCreated={onCreated} />,
  );
  return onCreated;
}

async function clickNext() {
  fireEvent.click(screen.getByTestId('wizard-next'));
}

describe('OnboardingWizard (TASK-358)', () => {
  it('blocks Continue until a mode (and preset) is chosen', () => {
    renderWizard();
    expect(screen.getByTestId('wizard-next')).toBeDisabled();
    fireEvent.click(screen.getByTestId('mode-preset'));
    expect(screen.getByTestId('wizard-next')).toBeDisabled();
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    expect(screen.getByTestId('wizard-next')).toBeEnabled();
  });

  it('agent options come from the adapters endpoint (no hardcoded single agent)', async () => {
    renderWizard();
    fireEvent.click(screen.getByTestId('mode-preset'));
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    await clickNext(); // → agent
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('Codex CLI')).toBeInTheDocument();
  });

  it('walks preset flow to review, starts a job and reports progress to created (TASK-362)', async () => {
    const onCreated = vi.fn();
    apiPost.mockImplementation(async (path: string) =>
      path.endsWith('/init') ? [{ job_id: 'job-xyz', name: 'proj-abc123' }] : [VALIDATE_OK]);
    renderWizard(onCreated);

    fireEvent.click(screen.getByTestId('mode-preset'));
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    await clickNext(); // agent
    fireEvent.click(screen.getByText('Codex CLI'));
    await clickNext(); // skills
    await clickNext(); // extra
    await clickNext(); // swimlanes — triggers validate
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    await clickNext(); // name
    fireEvent.click(screen.getByTestId('skip-name')); // don't know yet
    await clickNext(); // description
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'A product for testing wizards.' },
    });
    await clickNext(); // review
    await waitFor(() => expect(screen.getByTestId('wizard-create')).toBeEnabled());
    fireEvent.click(screen.getByTestId('wizard-create'));

    // Progress screen attaches an EventSource to the job stream.
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const stream = FakeEventSource.instances[0];
    expect(stream.url).toContain('/api/hub/init-jobs/job-xyz/events');
    stream.emit('log', { line: 'Installing claude adapter...' });
    stream.emit('phase', { phase: 'docs-seed' });
    await waitFor(() =>
      expect(screen.getByTestId('job-log')).toHaveTextContent('Installing claude adapter'),
    );
    expect(screen.getByText('Agent is processing your description & docs')).toBeInTheDocument();

    stream.emit('succeeded', { status: 'succeeded', result: { slug: 'proj-abc123' } });
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('proj-abc123'));

    const createCall = apiPost.mock.calls.find(([p]) => String(p).endsWith('/init'));
    expect(createCall?.[1]).toMatchObject({
      preset: 'nextjs-fastapi',
      stacks: [],
      agent: 'codex',
      name: '',
      description: 'A product for testing wizards.',
      background: true,
    });
  });

  it('cancel during a running job returns the UI to an actionable state', async () => {
    apiPost.mockImplementation(async (path: string) =>
      path.endsWith('/init') ? [{ job_id: 'job-c1', name: 'proj-x' }] : [VALIDATE_OK]);
    renderWizard();
    fireEvent.click(screen.getByTestId('mode-preset'));
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    for (let i = 0; i < 4; i += 1) await clickNext(); // agent→skills→extra→swimlanes
    await clickNext(); // name
    fireEvent.click(screen.getByTestId('skip-name'));
    await clickNext(); // description
    await clickNext(); // review
    await waitFor(() => expect(screen.getByTestId('wizard-create')).toBeEnabled());
    fireEvent.click(screen.getByTestId('wizard-create'));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));

    fireEvent.click(screen.getByTestId('job-cancel'));
    const cancelCall = apiPost.mock.calls.find(([p]) => String(p).includes('/cancel'));
    expect(cancelCall?.[0]).toContain('/api/hub/init-jobs/job-c1/cancel');

    FakeEventSource.instances[0].emit('cancelled', {
      status: 'cancelled', cleanup: { removed_dir: '/code/proj-x' },
    });
    await waitFor(() =>
      expect(screen.getByText(/partial scaffold was removed/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('job-back')); // actionable: back to review
    expect(screen.getByTestId('wizard-create')).toBeInTheDocument();
  });

  it('back navigation preserves chosen state', async () => {
    renderWizard();
    fireEvent.click(screen.getByTestId('mode-custom'));
    await clickNext(); // → stacks (custom-only step)
    fireEvent.click(screen.getByText('FastAPI'));
    fireEvent.click(screen.getByText('Go Fiber'));
    await clickNext(); // agent
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('button', { name: 'FastAPI' })).toHaveAttribute(
      'aria-pressed', 'true',
    );
    expect(screen.getByRole('button', { name: 'Go Fiber' })).toHaveAttribute(
      'aria-pressed', 'true',
    );
  });

  it('renders inline validation error from the dry-run at review', async () => {
    apiPost.mockRejectedValue(new Error('parent_dir is not writable: /code'));
    renderWizard();
    fireEvent.click(screen.getByTestId('mode-preset'));
    fireEvent.click(screen.getByText('Next.js + FastAPI full-stack'));
    for (let i = 0; i < 4; i += 1) await clickNext(); // agent→skills→extra→swimlanes
    await clickNext(); // name
    fireEvent.click(screen.getByTestId('skip-name'));
    await clickNext(); // description
    await clickNext(); // review — validate rejects
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('not writable'),
    );
    expect(screen.getByTestId('wizard-create')).toBeDisabled();
  });
});
