import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import SupportFooter from './SupportFooter';

describe('SupportFooter (TASK-372)', () => {
  it('renders repo, star, sponsor, coffee and crypto links in the footer landmark', () => {
    render(<SupportFooter />);
    expect(screen.getByRole('contentinfo')).toBeTruthy();
    expect(screen.getByRole('link', { name: /^github$/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /star/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /sponsor/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /coffee/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /crypto/i })).toBeTruthy();
  });

  it('opens external links safely (rel=noopener, target=_blank)', () => {
    render(<SupportFooter />);
    const sponsor = screen.getByRole('link', { name: /sponsor/i });
    expect(sponsor.getAttribute('rel')).toContain('noopener');
    expect(sponsor.getAttribute('target')).toBe('_blank');
  });
});
