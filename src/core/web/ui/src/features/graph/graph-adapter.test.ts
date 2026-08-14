import { describe, expect, it } from 'vitest';

import { buildGraph, type ApiGraphPayload } from './graph-adapter';

// — focus+context community-map styling. The no-root home runs
// the export in `processes` mode: synthetic `community` headers are the
// focus tier (forced label, hub size) and member nodes are de-emphasised
// context (no forced label, reduced size).
const communityPayload: ApiGraphPayload = {
  format: 'json',
  nodes: [
    { uid: 'community:a', kind: 'community', label: 'login-flow' },
    { uid: 'community:b', kind: 'community', label: 'billing-flow' },
    { uid: 'code:function:a.py::login', kind: 'code:function', label: 'login' },
    { uid: 'code:function:a.py::verify', kind: 'code:function', label: 'verify' },
  ],
  edges: [
    {
      source_uid: 'code:function:a.py::login',
      target_uid: 'community:a',
      edge_type: 'member_of_community',
    },
    {
      source_uid: 'code:function:a.py::verify',
      target_uid: 'community:a',
      edge_type: 'member_of_community',
    },
  ],
};

describe('buildGraph — community-map (processes) mode', () => {
  it('forces labels on community nodes but not on member nodes', () => {
    const g = buildGraph(communityPayload, { mode: 'processes' });
    expect(g.getNodeAttribute('community:a', 'forceLabel')).toBe(true);
    expect(g.getNodeAttribute('community:b', 'forceLabel')).toBe(true);
    expect(g.getNodeAttribute('code:function:a.py::login', 'forceLabel')).toBe(false);
    expect(g.getNodeAttribute('code:function:a.py::verify', 'forceLabel')).toBe(false);
  });

  it('de-emphasises member nodes — smaller than community headers', () => {
    const g = buildGraph(communityPayload, { mode: 'processes' });
    const headerSize = g.getNodeAttribute('community:a', 'size') as number;
    const memberSize = g.getNodeAttribute('code:function:a.py::login', 'size') as number;
    expect(memberSize).toBeLessThan(headerSize);
  });

  it('mutes member node color with an alpha suffix', () => {
    const g = buildGraph(communityPayload, { mode: 'processes' });
    const memberColor = g.getNodeAttribute('code:function:a.py::login', 'color') as string;
    // 8-digit hex (#RRGGBBAA) signals the de-emphasis blend.
    expect(memberColor).toMatch(/^#[0-9a-fA-F]{8}$/);
  });

  it('does not apply the de-emphasis dot size in the default auto mode', () => {
    const auto = buildGraph(communityPayload, { mode: 'auto' });
    const processes = buildGraph(communityPayload, { mode: 'processes' });
    // In auto mode members are degree-sized, not collapsed to the uniform
    // 3px context dot the community map uses.
    const autoMemberSize = auto.getNodeAttribute('code:function:a.py::login', 'size') as number;
    const mapMemberSize = processes.getNodeAttribute(
      'code:function:a.py::login',
      'size',
    ) as number;
    expect(autoMemberSize).toBeGreaterThan(mapMemberSize);
    // And member colors are not alpha-muted outside the community map.
    const autoColor = auto.getNodeAttribute('code:function:a.py::login', 'color') as string;
    expect(autoColor).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
});
