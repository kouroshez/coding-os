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
      chat_available: false,
      chat_missing: 'an in-process chat runtime',
      chat_remedy: '',
      dispatch_available: true,
      transcript_available: true,
      glyph: 'Cx',
      color: '#0891b2',
      models: [{ id: 'gpt-5.6-sol', label: 'gpt-5.6-sol', default: false }],
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

  it('groups models under their adapter', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('Anthropic Claude Code')).toBeInTheDocument();
    expect(screen.getByText('OpenAI Codex CLI')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Sonnet 4\.6/ })).toBeInTheDocument();
  });

  it('tells a chat-incapable adapter where it IS usable instead of promising it later', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));

    // The regression this guards: a working dispatcher advertised as vapourware.
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
    expect(screen.getByText('no live chat')).toBeInTheDocument();
    expect(screen.getByText(/Usable for roles and supervision/)).toBeInTheDocument();
  });

  it('states that live chat is unbuilt rather than describing the Hub streaming mechanism', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));

    // The regression this guards: copy about how the Hub streams reads as a
    // missing dependency or setting, so the reader hunts a Config toggle that
    // does not exist. An adapter with no remedy has nothing for them to do.
    expect(screen.queryByText(/in-process/i)).not.toBeInTheDocument();
    // No remedy means nothing to install, so it must not read as "Needs …".
    expect(screen.queryByText(/Needs /)).not.toBeInTheDocument();
    expect(screen.getByText(/Live chat with OpenAI Codex CLI is not built/)).toBeInTheDocument();
    expect(screen.getByText(/no setting or install enables it/)).toBeInTheDocument();
  });

  it('leaves a chat-incapable adapter model unselectable', () => {
    render(<ModelPicker value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));
    expect(screen.getByRole('option', { name: /gpt-5\.6-sol/ })).toBeDisabled();
  });

  it('selecting a model fires onChange with its id', () => {
    const onChange = vi.fn();
    render(<ModelPicker value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Opus 4\.8/ }));
    fireEvent.click(screen.getByRole('option', { name: /Sonnet 4\.6/ }));
    expect(onChange).toHaveBeenCalledWith('claude-sonnet-4-6');
  });
});
