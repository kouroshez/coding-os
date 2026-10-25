/**
 * Shapes of GET /api/memory (src/core/web/routes/memory.py) and the pure
 * grouping/filtering the Memory tab renders from them.
 */

export interface MemoryEntry {
  line: number;
  slug: string | null;
  title: string;
  rule: string;
}

export interface MemoryIndex {
  name: string;
  file: string;
  title: string;
  entries: MemoryEntry[];
  pointer?: { title: string; rule: string } | null;
}

export interface MemoryFile {
  slug: string;
  name: string | null;
  description: string | null;
  type: string | null;
  verified: string | null;
  links: string[];
  body: string;
}

export interface MemoryBudget {
  lines: number;
  bytes: number;
  max_lines: number;
  max_bytes: number;
}

export interface MemoryPayload {
  present: boolean;
  dir: string;
  budget?: MemoryBudget;
  indexes?: MemoryIndex[];
  memories?: MemoryFile[];
  lint?: { errors: string[]; warnings: string[]; summary: string };
}

export interface MemoryRow {
  entry: MemoryEntry;
  memory: MemoryFile | null;
  subIndex: MemoryIndex | null;
}

export interface MemoryGroup {
  index: MemoryIndex;
  rows: MemoryRow[];
}

/** Same window the lint applies to `verified` on project/reference memories. */
export const VERIFY_MAX_AGE_DAYS = 90;

const MS_PER_DAY = 86_400_000;

function matches(row: MemoryRow, needle: string): boolean {
  if (!needle) return true;
  const haystack = [
    row.entry.title,
    row.entry.rule,
    row.entry.slug ?? '',
    row.memory?.description ?? '',
    row.memory?.body ?? '',
  ]
    .join('\n')
    .toLowerCase();
  return haystack.includes(needle);
}

export function groupMemory(
  payload: MemoryPayload,
  query: string,
  type: string | null,
): MemoryGroup[] {
  const memories = new Map((payload.memories ?? []).map((m) => [m.slug, m]));
  const indexes = new Map((payload.indexes ?? []).map((i) => [i.name, i]));
  const needle = query.trim().toLowerCase();
  return (payload.indexes ?? [])
    .map((index) => ({
      index,
      rows: index.entries
        .map((entry) => ({
          entry,
          memory: entry.slug ? (memories.get(entry.slug) ?? null) : null,
          subIndex: entry.slug ? (indexes.get(entry.slug) ?? null) : null,
        }))
        .filter((row) => (type ? row.memory?.type === type : true))
        .filter((row) => matches(row, needle)),
    }))
    .filter((group) => group.rows.length > 0 || (!needle && !type));
}

export function unindexedMemories(payload: MemoryPayload): MemoryFile[] {
  const indexed = new Set(
    (payload.indexes ?? []).flatMap((i) => i.entries.map((e) => e.slug).filter(Boolean)),
  );
  return (payload.memories ?? []).filter((m) => !indexed.has(m.slug));
}

export function typeCounts(memories: MemoryFile[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const memory of memories) {
    const key = memory.type ?? 'untyped';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** Whole UTC days since a `YYYY-MM-DD` verified stamp; null when absent or unparseable. */
export function verifiedAgeDays(verified: string | null, now: Date = new Date()): number | null {
  if (!verified || !/^\d{4}-\d{2}-\d{2}$/.test(verified)) return null;
  const stamp = Date.parse(`${verified}T00:00:00Z`);
  if (Number.isNaN(stamp)) return null;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.floor((today - stamp) / MS_PER_DAY);
}

export function groupAnchor(name: string): string {
  return `memory-group-${name}`;
}

export function budgetRatio(used: number, max: number): number {
  return max > 0 ? Math.min(used / max, 1) : 0;
}
