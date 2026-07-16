import { describe, expect, it } from 'vitest';

import { liveSessionsBySid, visualFor } from './agentPresenceVisuals';
import type { AgentPresence } from './types';

const state = (sid: string, s: AgentPresence) => ({ sid, state: s });

describe('liveSessionsBySid', () => {
  it('keeps only active/working sessions — the states a card pip should pulse for', () => {
    const m = liveSessionsBySid([
      state('ses-claude-1', 'active'),
      state('ses-claude-2', 'working'),
      state('ses-claude-3', 'present'),
      state('ses-codex-4', 'offline'),
    ]);
    expect([...m.keys()]).toEqual(['ses-claude-1', 'ses-claude-2']);
    expect(m.get('ses-claude-1')?.state).toBe('active');
    expect(m.get('ses-claude-2')?.state).toBe('working');
  });

  it('bridges the chat deep-link to sdk_uuid when present, else the sid', () => {
    const m = liveSessionsBySid([
      { sid: 'ses-claude-1', state: 'active', sdk_uuid: 'uuid-42' },
      { sid: 'ses-claude-2', state: 'working', sdk_uuid: null },
    ]);
    expect(m.get('ses-claude-1')?.chatId).toBe('uuid-42');
    expect(m.get('ses-claude-2')?.chatId).toBe('ses-claude-2');
  });

  it('returns an empty map for undefined or empty inventories', () => {
    expect(liveSessionsBySid(undefined).size).toBe(0);
    expect(liveSessionsBySid([]).size).toBe(0);
  });
});

describe('visualFor', () => {
  it('falls back to offline visuals for unknown states', () => {
    expect(visualFor('mystery-state').label).toBe('offline');
    expect(visualFor(null).label).toBe('offline');
  });

  it('pulses for active and working, not for present/offline', () => {
    expect(visualFor('active').pulse).toBe(true);
    expect(visualFor('working').pulse).toBe(true);
    expect(visualFor('present').pulse).toBe(false);
    expect(visualFor('offline').pulse).toBe(false);
  });
});
