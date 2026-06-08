import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SubNav, subNavTabClass } from './HubPrimitives';

describe('SubNav', () => {
  it('centers the pill in a 3-column grid, not justify-between', () => {
    const { container } = render(
      <SubNav left={<span>L</span>} right={<span>R</span>}>
        <button>Tab</button>
      </SubNav>,
    );
    const grid = container.querySelector('.grid');
    expect(grid?.className).toContain('grid-cols-[1fr_auto_1fr]');
    expect(grid?.className).not.toContain('justify-between');

    // The middle column (the pill) is centered via the logical
    // justify-self utility so it mirrors correctly under RTL.
    const pill = container.querySelector('[class*="justify-self-center"]');
    expect(pill).toBeInTheDocument();
    expect(pill?.textContent).toContain('Tab');
  });

  it('exposes a tablist role + aria-label only when tablist is set', () => {
    const { rerender } = render(
      <SubNav>
        <button>T</button>
      </SubNav>,
    );
    expect(screen.queryByRole('tablist')).toBeNull();

    rerender(
      <SubNav tablist ariaLabel="Cognition views">
        <button role="tab">T</button>
      </SubNav>,
    );
    expect(screen.getByRole('tablist')).toHaveAttribute('aria-label', 'Cognition views');
  });

  it('renders the left and right slots', () => {
    render(
      <SubNav left={<span>LEFT</span>} right={<span>RIGHT</span>}>
        <button>T</button>
      </SubNav>,
    );
    expect(screen.getByText('LEFT')).toBeInTheDocument();
    expect(screen.getByText('RIGHT')).toBeInTheDocument();
  });
});

describe('subNavTabClass', () => {
  it('fills the active tab with the accent and mutes the inactive tab', () => {
    expect(subNavTabClass(true)).toContain('bg-[var(--cos-accent)]');
    expect(subNavTabClass(true)).toContain('text-white');
    expect(subNavTabClass(false)).toContain('text-[var(--cos-muted)]');
    expect(subNavTabClass(false)).not.toContain('bg-[var(--cos-accent)]');
  });

  it('is never uppercase or monospace (de-mono enterprise type)', () => {
    expect(subNavTabClass(false)).not.toContain('uppercase');
    expect(subNavTabClass(false)).not.toContain('font-mono');
  });
});
