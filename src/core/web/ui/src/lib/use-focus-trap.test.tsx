import { useRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useFocusTrap } from './use-focus-trap';

function Harness({ active, onClose }: { active: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, { active, onClose });
  return (
    <div ref={ref}>
      <button>first</button>
      <button>last</button>
    </div>
  );
}

describe('useFocusTrap', () => {
  it('locks scroll and focuses the first focusable when active', () => {
    render(<Harness active onClose={vi.fn()} />);
    expect(document.body.style.overflow).toBe('hidden');
    expect(document.activeElement).toBe(screen.getByText('first'));
  });

  it('closes on Escape while active', () => {
    const onClose = vi.fn();
    render(<Harness active onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('is inert while inactive', () => {
    const onClose = vi.fn();
    render(<Harness active={false} onClose={onClose} />);
    expect(document.body.style.overflow).not.toBe('hidden');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('restores scroll on unmount', () => {
    const { unmount } = render(<Harness active onClose={vi.fn()} />);
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('');
  });
});
