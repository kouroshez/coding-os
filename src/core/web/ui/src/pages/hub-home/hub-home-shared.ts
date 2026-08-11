import { useCallback, useState } from 'react';

export function useBusy(): [boolean, <T>(fn: () => Promise<T>) => Promise<T>] {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  }, []);
  return [busy, run];
}


export function slugifyProjectName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '');
}

export const stroke = { strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

export const PROJECT_SHORTCUTS = [
  { key: 'chat', label: 'Chat', path: 'workspace/chat' },
  { key: 'board', label: 'Board', path: 'workspace/board' },
  { key: 'graph', label: 'Graph', path: 'graph' },
  { key: 'search', label: 'Search', path: 'workspace/search' },
] as const;

