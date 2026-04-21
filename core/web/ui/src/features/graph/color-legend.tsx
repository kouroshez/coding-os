import { useState } from 'react';
import { ALL_KINDS, kindColor } from '@/lib/node-colors';

// Floating color legend, collapsible to save canvas real estate.
export default function ColorLegend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded border border-[#2a2f39] bg-[#151a22]/95 text-xs shadow-lg backdrop-blur">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-2 py-1 text-[#9ea4ae] hover:text-white"
      >
        <span>Legend</span>
        <span aria-hidden>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ul className="max-h-64 overflow-auto border-t border-[#2a2f39] p-2 cos-scroll">
          {ALL_KINDS.map((k) => (
            <li key={k} className="flex items-center gap-2 py-0.5">
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ background: kindColor(k) }}
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
