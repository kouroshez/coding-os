import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import ViewModeTabs from './view-mode-tabs';
import { useGraphStore } from '@/store/graph-store';

describe('ViewModeTabs a11y (WAI-ARIA tabs)', () => {
  beforeEach(() => {
    useGraphStore.getState().setViewMode('auto');
  });

  it('renders a tablist with roving tabindex (only the active tab is tabbable)', () => {
    render(<ViewModeTabs />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(4);

    const auto = screen.getByRole('tab', { name: 'Auto' });
    expect(auto).toHaveAttribute('aria-selected', 'true');
    expect(auto).toHaveAttribute('tabindex', '0');

    const containment = screen.getByRole('tab', { name: 'Containment' });
    expect(containment).toHaveAttribute('aria-selected', 'false');
    expect(containment).toHaveAttribute('tabindex', '-1');
  });

  it('ArrowRight moves selection to the next tab', () => {
    render(<ViewModeTabs />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Auto' }), { key: 'ArrowRight' });
    expect(useGraphStore.getState().viewMode).toBe('containment');
    expect(screen.getByRole('tab', { name: 'Containment' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('ArrowLeft from the first tab wraps to the last', () => {
    render(<ViewModeTabs />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Auto' }), { key: 'ArrowLeft' });
    expect(useGraphStore.getState().viewMode).toBe('processes');
  });
});
