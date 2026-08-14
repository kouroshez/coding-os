/**
 * The picker is only correct if the URL it produces *resolves* in the real
 * router. Asserting on navigate()'s argument would have passed for `chat`
 * while the user still landed on Hub home, because `/p/<slug>/chat` matched
 * no route and fell through to the `*` catch-all.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import NeedProjectPage from './NeedProjectPage';
import { projectFeaturePath } from '@/lib/use-scoped-link';
import { RedirectToWorkspace } from '@/lib/route-redirects';

const PROJECTS = { projects: [{ slug: 'coding-os', path: '/Users/x/coding-os' }], count: 1 };

// Every feature the unscoped router hands to NeedProjectPage, paired with the
// project-scoped route that must exist for it in App.tsx.
const FEATURES: Array<[string, string]> = [
  ['chat', '/p/coding-os/workspace/chat'],
  ['board', '/p/coding-os/workspace/board'],
  ['search', '/p/coding-os/workspace/search'],
  ['memory', '/p/coding-os/workspace/memory'],
  ['graph', '/p/coding-os/graph'],
  ['cognition', '/p/coding-os/cognition'],
  ['config', '/p/coding-os/config'],
];

function LocationProbe() {
  const { pathname, search } = useLocation();
  return <div data-testid="loc">{pathname + search}</div>;
}

function renderPicker(feature: string, at: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // A Route `path` is pathname-only; the query rides on initialEntries.
  const routePath = at.split('?')[0];
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <LocationProbe />
        <Routes>
          <Route path={routePath} element={<NeedProjectPage feature={feature} />} />
          {/* The real destinations. Anything the picker emits that is not one
              of these would fall through here, exactly as it did in prod. */}
          <Route path="/p/:slug/workspace/:tab" element={<div>workspace-tab</div>} />
          <Route path="/p/:slug/:feature" element={<div>standalone</div>} />
          <Route path="*" element={<div>HUB-HOME-FALLBACK</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(PROJECTS), { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('NeedProjectPage → project-scoped route', () => {
  it.each(FEATURES)('picking a project from %s lands on %s', async (feature, expected) => {
    renderPicker(feature, `/${feature}`);
    const open = await screen.findByRole('button', { name: /coding-os/ });
    fireEvent.click(open);
    await waitFor(() => expect(screen.getByTestId('loc')).toHaveTextContent(expected));
    expect(screen.queryByText('HUB-HOME-FALLBACK')).toBeNull();
  });

  it('keeps the deep-link query string across the pick', async () => {
    renderPicker('graph', '/graph?view=impact');
    fireEvent.click(await screen.findByRole('button', { name: /coding-os/ }));
    await waitFor(() =>
      expect(screen.getByTestId('loc')).toHaveTextContent('/p/coding-os/graph?view=impact'),
    );
  });
});

describe('flat /p/<slug>/<tab> deep links', () => {
  // Bookmarks, shared links and older Quick Actions still use the flat form.
  // Before the fix these matched no route and the `*` catch-all sent them home.
  function renderFlat(entry: string) {
    return render(
      <MemoryRouter initialEntries={[entry]}>
        <LocationProbe />
        <Routes>
          <Route path="/p/:slug/chat" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/chat/:sessionId" element={<RedirectToWorkspace sub="chat" />} />
          <Route path="/p/:slug/memory" element={<RedirectToWorkspace sub="memory" />} />
          <Route path="/p/:slug/workspace/:tab" element={<div>tab</div>} />
          <Route path="/p/:slug/workspace/:tab/:sessionId" element={<div>tab-deep</div>} />
          <Route path="*" element={<div>HUB-HOME-FALLBACK</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it.each([
    ['/p/coding-os/chat', '/p/coding-os/workspace/chat'],
    ['/p/coding-os/memory', '/p/coding-os/workspace/memory'],
  ])('%s redirects into the workspace tab', (from, to) => {
    renderFlat(from);
    expect(screen.getByTestId('loc')).toHaveTextContent(to);
    expect(screen.queryByText('HUB-HOME-FALLBACK')).toBeNull();
  });

  it('carries the query string and the session id across the redirect', () => {
    renderFlat('/p/coding-os/chat/ses-42?view=chat');
    expect(screen.getByTestId('loc')).toHaveTextContent(
      '/p/coding-os/workspace/chat/ses-42?view=chat',
    );
  });
});

describe('projectFeaturePath', () => {
  it('nests workspace tabs and leaves standalone features flat', () => {
    expect(projectFeaturePath('chat', 'a')).toBe('/p/a/workspace/chat');
    expect(projectFeaturePath('memory', 'a')).toBe('/p/a/workspace/memory');
    expect(projectFeaturePath('graph', 'a')).toBe('/p/a/graph');
  });

  it('encodes a slug containing a slash or space', () => {
    expect(projectFeaturePath('chat', 'my repo/x')).toBe('/p/my%20repo%2Fx/workspace/chat');
  });
});
