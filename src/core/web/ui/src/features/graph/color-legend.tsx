import { useState } from 'react';
import { ALL_KINDS, kindColor, ROOT_COLOR } from '@/lib/node-colors';
import { useThemeStore } from '@/store/theme-store';

// Floating color legend, collapsible to save canvas real estate.
export default function ColorLegend() {
  const [open, setOpen] = useState(false);
  const theme = useThemeStore((s) => s.theme);

  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-2 py-1 text-[var(--cos-muted)] hover:text-white"
      >
        <span>Legend</span>
        <span aria-hidden>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ul className="max-h-64 overflow-auto border-t border-[var(--cos-border)] p-2 cos-scroll">
          {/* Reserved focal anchor — not a categorical kind (TASK-408). */}
          <li className="flex items-center gap-2 py-0.5 font-medium text-[var(--cos-text)]">
            <span
              className="inline-block h-2 w-2 rounded-full ring-1 ring-white/70"
              style={{ background: ROOT_COLOR }}
              aria-hidden
            />
            <span>project root</span>
          </li>
          {ALL_KINDS.map((k) => (
            <li key={k} className="flex items-center gap-2 py-0.5">
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ background: kindColor(k, theme) }}
                aria-hidden
              />
              <span>{k}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
