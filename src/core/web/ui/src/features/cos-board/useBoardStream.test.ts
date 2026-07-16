import { describe, expect, it } from 'vitest';

import { agentForSession, liveRowKey } from './useBoardStream';

// The manifest ids the UI receives from /api/board/list `agent_manifest`.
// `human` is the trailing row and the no-match fallback.
const MANIFEST_IDS = ['claude', 'codex', 'human'] as const;

describe('agentForSession', () => {
  it('attributes a session to the manifest id embedded in it', () => {
    expect(agentForSession('ses-claude-2026', MANIFEST_IDS)).toBe('claude');
    expect(agentForSession('ses-codex-abc', MANIFEST_IDS)).toBe('codex');
  });

  it('falls back to human for empty / unknown sessions', () => {
    expect(agentForSession(null, MANIFEST_IDS)).toBe('human');
    expect(agentForSession(undefined, MANIFEST_IDS)).toBe('human');
    expect(agentForSession('local-mac', MANIFEST_IDS)).toBe('human');
  });

  it('attributes a future adapter id present only in the manifest, with no code edits here', () => {
    const withGemini = [...MANIFEST_IDS, 'gemini'];
    expect(agentForSession('ses-gemini-9001', withGemini)).toBe('gemini');
    // The same session is unattributable without the manifest entry — proving
    // the resolution is data-driven, not a hardcoded literal list.
    expect(agentForSession('ses-gemini-9001', MANIFEST_IDS)).toBe('human');
  });

  it('prefers the longest matching id so a superstring id is not shadowed', () => {
    const ids = ['claude', 'claude-sdk', 'human'];
    expect(agentForSession('ses-claude-sdk-42', ids)).toBe('claude-sdk');
    expect(agentForSession('ses-claude-42', ids)).toBe('claude');
  });

  it('attributes ses-system-* maintenance sessions to the system manifest row', () => {
    const withSystem = [...MANIFEST_IDS, 'system'];
    expect(agentForSession('ses-system-auto-archive', withSystem)).toBe('system');
    expect(agentForSession('ses-system-reclaim', withSystem)).toBe('system');
    // Without the manifest row (older Hub payload) the session falls back to
    // human — the data-driven contract, same as the gemini case above.
    expect(agentForSession('ses-system-auto-archive', MANIFEST_IDS)).toBe('human');
  });
});

describe('liveRowKey', () => {
  it('matches two file-edit rows that render identically (phantom-row collapse)', () => {
    const a = { kind: 'task-updated' as const, taskId: 'TASK-392', message: '? -> in_progress' };
    const b = { kind: 'task-updated' as const, taskId: 'TASK-392', message: '? -> in_progress' };
    expect(liveRowKey(a)).toBe(liveRowKey(b));
  });

  it('distinguishes a different task, status, or kind', () => {
    const base = { kind: 'task-updated' as const, taskId: 'TASK-392', message: '? -> in_progress' };
    expect(liveRowKey(base)).not.toBe(
      liveRowKey({ ...base, taskId: 'TASK-393' }),
    );
    expect(liveRowKey(base)).not.toBe(
      liveRowKey({ ...base, message: 'ready -> in_progress' }),
    );
    expect(liveRowKey(base)).not.toBe(
      liveRowKey({ ...base, kind: 'task-created' as const }),
    );
  });
});
