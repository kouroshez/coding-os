import { useCallback, useEffect, useRef, useState } from 'react';

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 1.5;
const ZOOM_STEP = 0.1;

function clampZoom(v: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(v * 100) / 100));
}

/**
 * Persisted board view state: zoom level, collapsed swimlanes, and the
 * keyboard shortcuts that drive both (⌘±/⌘0 zoom, `n` new task).
 */
export function useBoardViewState(onNewTask: () => void) {
  const [zoom, setZoomRaw] = useState<number>(() => {
    const v = parseFloat(localStorage.getItem('cos-zoom') || '1');
    return Number.isFinite(v) && v >= ZOOM_MIN && v <= ZOOM_MAX ? v : 1;
  });
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('cos-collapsed-lanes') || '[]') as string[]);
    } catch {
      return new Set();
    }
  });

  useEffect(() => {
    localStorage.setItem('cos-zoom', String(zoom));
  }, [zoom]);
  useEffect(() => {
    localStorage.setItem('cos-collapsed-lanes', JSON.stringify([...collapsed]));
  }, [collapsed]);

  // Ref-held so the listener stays mounted once for the page's lifetime
  // instead of re-binding whenever the parent re-renders a new callback.
  const newTask = useRef(onNewTask);
  newTask.current = onNewTask;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (e.key === 'n' && !e.metaKey && !e.ctrlKey && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        e.preventDefault();
        newTask.current();
      }
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === '=' || e.key === '+') {
        e.preventDefault();
        setZoomRaw((z) => clampZoom(z + ZOOM_STEP));
      } else if (e.key === '-') {
        e.preventDefault();
        setZoomRaw((z) => clampZoom(z - ZOOM_STEP));
      } else if (e.key === '0') {
        e.preventDefault();
        setZoomRaw(1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const setZoom = useCallback((v: number) => setZoomRaw(clampZoom(v)), []);

  const collapseLane = useCallback((laneId: string) => {
    setCollapsed((prev) => new Set(prev).add(laneId));
  }, []);
  const expandLane = useCallback((laneId: string) => {
    setCollapsed((prev) => {
      const n = new Set(prev);
      n.delete(laneId);
      return n;
    });
  }, []);

  return { zoom, setZoom, collapsed, setCollapsed, collapseLane, expandLane };
}

export type BoardViewState = ReturnType<typeof useBoardViewState>;
