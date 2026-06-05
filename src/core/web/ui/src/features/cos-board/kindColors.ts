/** Sticky-note palette per kind — from newdesign/fixtures.jsx */
export interface KindStyle {
  bg: string;
  bg2: string;
  chip: string;
  label: string;
}

// bg/bg2 = card gradient (themed --sticky-* tints); chip = themed --kind-*
// ink (AA on both the light and dark tint). No hardcoded hex — so a card
// reads correctly in either theme (Cortex Phase 2).
export const KIND_COLORS: Record<string, KindStyle> = {
  bug: { bg: 'var(--sticky-red)', bg2: 'var(--sticky-red-2)', chip: 'var(--kind-bug)', label: 'bug' },
  feature: {
    bg: 'var(--sticky-yellow)',
    bg2: 'var(--sticky-yellow-2)',
    chip: 'var(--kind-feature)',
    label: 'feat',
  },
  chore: { bg: 'var(--sticky-green)', bg2: 'var(--sticky-green-2)', chip: 'var(--kind-chore)', label: 'chore' },
  spike: { bg: 'var(--sticky-blue)', bg2: 'var(--sticky-blue-2)', chip: 'var(--kind-spike)', label: 'spike' },
  docs: { bg: 'var(--sticky-purple)', bg2: 'var(--sticky-purple-2)', chip: 'var(--kind-docs)', label: 'docs' },
  refactor: { bg: 'var(--sticky-teal)', bg2: 'var(--sticky-teal-2)', chip: 'var(--kind-refactor)', label: 'refactor' },
  test: { bg: 'var(--sticky-orange)', bg2: 'var(--sticky-orange-2)', chip: 'var(--kind-test)', label: 'test' },
  security: { bg: 'var(--sticky-orange)', bg2: 'var(--sticky-orange-2)', chip: 'var(--kind-security)', label: 'sec' },
};

export function kindStyle(kind: string | undefined): KindStyle {
  return KIND_COLORS[kind || ''] || KIND_COLORS.feature;
}
