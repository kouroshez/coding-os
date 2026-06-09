import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

let mockData: unknown;
vi.mock('@/lib/hooks', () => ({ useApiGet: () => ({ data: mockData }) }));

import EffortPicker from './EffortPicker';

describe('EffortPicker', () => {
  it('renders the adapter effort levels when it declares them', () => {
    mockData = {
      adapters: [
        {
          id: 'claude',
          available: true,
          models: [{ id: 'claude-opus-4-8' }],
          efforts: ['low', 'high', 'max'],
          default_effort: 'high',
        },
      ],
    };
    render(<EffortPicker model="claude-opus-4-8" value="" onChange={() => {}} />);
    expect(screen.getByRole('combobox', { name: /reasoning effort/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'max' })).toBeInTheDocument();
  });

  it('renders nothing when the active adapter has no effort levels', () => {
    mockData = {
      adapters: [{ id: 'codex', available: true, models: [{ id: 'gpt-x' }], efforts: [] }],
    };
    const { container } = render(<EffortPicker model="gpt-x" value="" onChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
