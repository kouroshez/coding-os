import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const hoisted = vi.hoisted(() => ({ data: null as unknown }));
vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: hoisted.data, error: null, isLoading: false }),
}));

import OnboardingCard from './OnboardingCard';

describe('OnboardingCard', () => {
  it('renders the hero + CTA when onboarding is incomplete', () => {
    hoisted.data = { complete: false, placeholders_remaining: 3 };
    const onStart = vi.fn();
    render(<OnboardingCard onStart={onStart} />);
    expect(screen.getByText(/set up your project/i)).toBeInTheDocument();
    expect(screen.getByText(/3 to fill/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /set up your docs/i }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when onboarding is complete', () => {
    hoisted.data = { complete: true };
    const { container } = render(<OnboardingCard onStart={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing before data loads', () => {
    hoisted.data = null;
    const { container } = render(<OnboardingCard onStart={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('dismiss hides the hero', () => {
    hoisted.data = { complete: false, placeholders_remaining: 1 };
    render(<OnboardingCard onStart={() => {}} />);
    fireEvent.click(screen.getByLabelText(/dismiss onboarding/i));
    expect(screen.queryByText(/set up your project/i)).toBeNull();
  });
});
