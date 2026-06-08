import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Modal } from './Modal';

function renderOpen(extra?: { onClose?: () => void; title?: string }) {
  const onClose = extra?.onClose ?? vi.fn();
  render(
    <Modal open onClose={onClose} title={extra?.title} footer={<button>Save</button>}>
      <p>Body content</p>
      <button>Inside</button>
    </Modal>,
  );
  return { onClose };
}

describe('Modal', () => {
  it('renders nothing when closed', () => {
    render(
      <Modal open={false} onClose={vi.fn()}>
        <p>hidden</p>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText('hidden')).toBeNull();
  });

  it('exposes dialog a11y semantics when open', () => {
    renderOpen({ title: 'Task TASK-001' });
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby');
    expect(screen.getByRole('heading', { name: 'Task TASK-001' })).toBeInTheDocument();
  });

  it('omits aria-labelledby when there is no title', () => {
    renderOpen();
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-labelledby');
  });

  it('closes on Escape', () => {
    const { onClose } = renderOpen({ title: 'T' });
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on the Close button', () => {
    const { onClose } = renderOpen({ title: 'T' });
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on a backdrop click but not on a click inside the card', () => {
    const { onClose } = renderOpen({ title: 'T' });
    const dialog = screen.getByRole('dialog');
    const container = dialog.parentElement as HTMLElement;

    fireEvent.mouseDown(dialog);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.mouseDown(container);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders body and footer slots', () => {
    renderOpen({ title: 'T' });
    expect(screen.getByText('Body content')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });
});
