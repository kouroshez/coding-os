import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useRovingTabList } from './use-roving-tablist';

function Harness({ onSelect }: { onSelect: (i: number) => void }) {
  const labels = ['One', 'Two', 'Three'];
  const { tabRefs, onKeyDown } = useRovingTabList(labels.length, onSelect);
  return (
    <div role="tablist">
      {labels.map((l, i) => (
        <button
          key={l}
          ref={(el) => {
            tabRefs.current[i] = el;
          }}
          role="tab"
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

describe('useRovingTabList (WAI-ARIA tab keyboard model)', () => {
  it('ArrowRight / ArrowDown select the next tab', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'One' }), { key: 'ArrowRight' });
    expect(onSelect).toHaveBeenLastCalledWith(1);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Two' }), { key: 'ArrowDown' });
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it('ArrowLeft from the first tab wraps to the last', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'One' }), { key: 'ArrowLeft' });
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('ArrowRight from the last tab wraps to the first', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Three' }), { key: 'ArrowRight' });
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it('Home selects the first tab, End selects the last', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Two' }), { key: 'Home' });
    expect(onSelect).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Two' }), { key: 'End' });
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it('ignores non-navigation keys', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'One' }), { key: 'x' });
    expect(onSelect).not.toHaveBeenCalled();
  });
});
