import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import DesignComingSoon from './DesignComingSoon';

describe('DesignComingSoon (TASK-372)', () => {
  it('renders an h1 Design heading, a coming-soon h2, and names ADR-0008', () => {
    render(<DesignComingSoon />);
    expect(screen.getByRole('heading', { level: 1, name: /design/i })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2, name: /coming soon/i })).toBeTruthy();
    expect(screen.getByText(/ADR-0008/)).toBeTruthy();
  });
});
