import { describe, expect, it } from 'vitest';
import { collapseRepeats, isCommitEcho } from './task-history';

const worklog = (text: string, at = 0, actor = 'claude') => ({
  type: 'worklog' as const,
  at,
  text,
  actor: { type: 'agent', id: actor, label: actor },
});

describe('isCommitEcho', () => {
  it('drops a worklog bullet echoing a known commit (worklog sha longer)', () => {
    expect(isCommitEcho(worklog('commit fe32399c57 — ci: fix parse'), ['fe32399c'])).toBe(true);
  });

  it('drops a "committed" bullet when the known sha is longer', () => {
    expect(isCommitEcho(worklog('committed 135cfaf8 · 2 files'), ['135cfaf8ab'])).toBe(true);
  });

  it('keeps a commit-shaped bullet whose sha matches no commit row', () => {
    expect(isCommitEcho(worklog('commit deadbeef1 — unrelated'), ['fe32399c'])).toBe(false);
  });

  it('keeps ordinary worklog bullets and non-worklog events', () => {
    expect(isCommitEcho(worklog('Edit ci.yml'), ['fe32399c'])).toBe(false);
    expect(isCommitEcho({ type: 'status', at: 0, to: 'testing' }, ['fe32399c'])).toBe(false);
  });
});

describe('collapseRepeats', () => {
  it('collapses consecutive identical worklog bullets and keeps the newest timestamp', () => {
    const rows = collapseRepeats([worklog('Edit ci.yml', 1), worklog('Edit ci.yml', 2), worklog('Edit ci.yml', 3)]);
    expect(rows).toHaveLength(1);
    expect(rows[0].repeats).toBe(3);
    expect(rows[0].event.at).toBe(3);
  });

  it('does not collapse across different actors or interleaved events', () => {
    const rows = collapseRepeats([
      worklog('Edit ci.yml', 1),
      worklog('Edit ci.yml', 2, 'codex'),
      worklog('Edit ci.yml', 3),
    ]);
    expect(rows).toHaveLength(3);
  });

  it('never collapses commit or status events', () => {
    const commit = { type: 'commit' as const, at: 1, sha: 'abc1234', subject: 's' };
    const rows = collapseRepeats([commit, { ...commit }]);
    expect(rows).toHaveLength(2);
  });
});
