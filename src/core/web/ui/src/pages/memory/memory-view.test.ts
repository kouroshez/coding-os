import { describe, expect, it } from 'vitest';
import {
  budgetRatio,
  groupMemory,
  typeCounts,
  unindexedMemories,
  verifiedAgeDays,
  type MemoryFile,
  type MemoryPayload,
} from './memory-view';

function memory(slug: string, type: string | null, body = ''): MemoryFile {
  return { slug, name: slug, description: `about ${slug}`, type, verified: null, links: [], body };
}

const payload: MemoryPayload = {
  present: true,
  dir: '.agents/memory',
  indexes: [
    {
      name: 'MEMORY',
      file: 'MEMORY.md',
      title: 'Memory Index',
      entries: [
        { line: 3, slug: 'keep-tests-light', title: 'Keep tests light', rule: 'one heavy process' },
        { line: 4, slug: 'index-browser', title: 'Browser work', rule: 'before a browser' },
      ],
    },
    {
      name: 'index-browser',
      file: 'index-browser.md',
      title: 'Browser work',
      entries: [{ line: 3, slug: 'use-the-extension', title: 'Use the extension', rule: 'attach' }],
      pointer: { title: 'Browser work', rule: 'before a browser' },
    },
  ],
  memories: [
    memory('keep-tests-light', 'feedback', 'macOS has no OOM killer'),
    memory('use-the-extension', 'reference'),
    memory('orphan-note', 'user'),
  ],
};

describe('groupMemory', () => {
  it('resolves each entry to its memory or its sub-index', () => {
    const [root, sub] = groupMemory(payload, '', null);
    expect(root.rows.map((r) => r.memory?.slug ?? r.subIndex?.name)).toEqual([
      'keep-tests-light',
      'index-browser',
    ]);
    expect(sub.rows[0].memory?.type).toBe('reference');
  });

  it('filters on body text and drops groups left empty', () => {
    const groups = groupMemory(payload, 'OOM', null);
    expect(groups).toHaveLength(1);
    expect(groups[0].rows.map((r) => r.entry.slug)).toEqual(['keep-tests-light']);
  });

  it('a type filter hides sub-index pointer rows', () => {
    const groups = groupMemory(payload, '', 'reference');
    expect(groups.map((g) => g.index.name)).toEqual(['index-browser']);
  });
});

describe('derived counts', () => {
  it('lists memories no index links', () => {
    expect(unindexedMemories(payload).map((m) => m.slug)).toEqual(['orphan-note']);
  });

  it('counts types, largest first then by name', () => {
    expect(typeCounts([...payload.memories!, memory('x', 'feedback'), memory('y', null)])).toEqual([
      ['feedback', 2],
      ['reference', 1],
      ['untyped', 1],
      ['user', 1],
    ]);
  });
});

describe('verifiedAgeDays', () => {
  const now = new Date('2026-10-25T03:00:00Z');

  it('counts whole UTC days', () => {
    expect(verifiedAgeDays('2026-10-01', now)).toBe(24);
    expect(verifiedAgeDays('2026-10-25', now)).toBe(0);
  });

  it('returns null for a missing or malformed stamp', () => {
    expect(verifiedAgeDays(null, now)).toBeNull();
    expect(verifiedAgeDays('last week', now)).toBeNull();
  });
});

describe('budgetRatio', () => {
  it('caps at 1 and survives a zero limit', () => {
    expect(budgetRatio(33, 200)).toBeCloseTo(0.165);
    expect(budgetRatio(300, 200)).toBe(1);
    expect(budgetRatio(5, 0)).toBe(0);
  });
});
