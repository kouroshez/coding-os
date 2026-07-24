import { useRef, type KeyboardEvent } from 'react';

// WAI-ARIA tabs keyboard model shared by every Hub tablist (graph view-mode,
// Config sections, Observability tabs). Arrow/Home/End move focus + selection
// across the tabs; roving tabindex means only the active tab is in the Tab
// order. Callers own their active state (URL param / useState / store) and pass
// onSelect so this stays store-agnostic.
export function useRovingTabList(
  count: number,
  onSelect: (index: number) => void,
) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = count - 1;
    let next = index;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = index === last ? 0 : index + 1;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = index === 0 ? last : index - 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = last;
    else return;
    e.preventDefault();
    onSelect(next);
    tabRefs.current[next]?.focus();
  };

  return { tabRefs, onKeyDown };
}
