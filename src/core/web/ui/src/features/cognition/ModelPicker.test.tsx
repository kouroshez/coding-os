import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const PAYLOAD = {
  adapters: [
    {
      id: 'claude',
      label: 'Anthropic Claude Code',
      runtime: 'in_process',
      available: true,
      glyph: 'Cl',
      color: '#d97706',
      models: [
        { id: 'claude-opus-4-8', label: 'Opus 4.8', default: true },
        { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6', default: false },
      ],
    },
    {
      id: 'codex',
      label: 'OpenAI Codex CLI',
      runtime: 'roadmap',
      available: false,
      glyph: 'Cx',
      color: '#0891b2',
      models: [],
    },
  ],
  default_model: 'claude-opus-4-8',
  count: 2,
};

vi.mock('@/lib/hooks', () => ({
  useApiGet: () => ({ data: PAYLOAD, isLoading: false, error: null }),
}));

import ModelPicker from './ModelPicker';

describe('ModelPicker', () => {
  it('shows the adapter default model on the trigger when value is empty', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Opus 4\.8/ })).toBeInTheDocument();
  });

  it('groups models under their adapter and marks roadmap adapters coming soon', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('Anthropic Claude Code')).toBeInTheDocument();
    expect(screen.getByText('OpenAI Codex CLI')).toBeInTheDocument();
    expect(screen.getByText('coming soon')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Sonnet 4\.6/ })).toBeInTheDocument();
  });

  it('selecting a model fires onChange with its id', () => {
    const onChange = vi.fn();
    render(<ModelPicker value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));
    fireEvent.click(screen.getByRole('option', { name: /Sonnet 4\.6/ }));
    expect(onChange).toHaveBeenCalledWith('claude-sonnet-4-6');
  });
});
