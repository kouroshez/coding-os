import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import SupportFooter from './SupportFooter';

describe('SupportFooter (TASK-372)', () => {
  it('renders only real, resolving links (repo, star, sponsor) in the footer landmark', () => {
    render(<SupportFooter />);
    expect(screen.getByRole('contentinfo')).toBeTruthy();
    const github = screen.getByRole('link', { name: /^github$/i });
    expect(github.getAttribute('href')).toContain('kouroshez');
    expect(screen.getByRole('link', { name: /star/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /sponsor/i })).toBeTruthy();
    // Payment placeholders (buy-me-a-coffee TODO handle, crypto) were dropped
    // rather than shipped as 404s — assert they are gone (TASK-836).
    expect(screen.queryByRole('link', { name: /coffee/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /crypto/i })).toBeNull();
  });

  it('opens external links safely (rel=noopener, target=_blank)', () => {
    render(<SupportFooter />);
    const sponsor = screen.getByRole('link', { name: /sponsor/i });
    expect(sponsor.getAttribute('rel')).toContain('noopener');
    expect(sponsor.getAttribute('target')).toBe('_blank');
  });
});
