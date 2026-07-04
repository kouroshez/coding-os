import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import MarketplacePage from './MarketplacePage';

describe('MarketplacePage (TASK-786)', () => {
  it('renders a Marketplace h1, a coming-soon h2, and names the Extension Manager doc', () => {
    render(<MarketplacePage />);
    expect(screen.getByRole('heading', { level: 1, name: /marketplace/i })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2, name: /coming soon/i })).toBeTruthy();
    expect(screen.getByText(/extension-manager\.md/)).toBeTruthy();
  });
});
