// Recent-query ring buffer in localStorage.

export const RECENT_KEY = 'cos.search.recent';
export const RECENT_LIMIT = 8;

export function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, RECENT_LIMIT) : [];
  } catch {
    return [];
  }
}
export function pushRecent(q: string): string[] {
  const next = [q, ...loadRecent().filter((r) => r !== q)].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // localStorage quota / disabled — non-fatal
  }
  return next;
}

