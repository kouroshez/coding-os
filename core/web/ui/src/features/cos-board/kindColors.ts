/** Sticky-note palette per kind — from newdesign/fixtures.jsx */
export interface KindStyle {
  bg: string;
  bg2: string;
  chip: string;
  label: string;
}

export const KIND_COLORS: Record<string, KindStyle> = {
  bug: { bg: 'var(--sticky-red)', bg2: 'var(--sticky-red-2)', chip: '#b91c1c', label: 'bug' },
  feature: {
    bg: 'var(--sticky-yellow)',
    bg2: 'var(--sticky-yellow-2)',
    chip: '#a16207',
    label: 'feat',
  },
  chore: { bg: 'var(--sticky-green)', bg2: 'var(--sticky-green-2)', chip: '#15803d', label: 'chore' },
  spike: { bg: 'var(--sticky-blue)', bg2: 'var(--sticky-blue-2)', chip: '#1d4ed8', label: 'spike' },
  docs: { bg: 'var(--sticky-purple)', bg2: 'var(--sticky-purple-2)', chip: '#7e22ce', label: 'docs' },
  refactor: { bg: 'var(--sticky-teal)', bg2: '#5eead4', chip: '#0f766e', label: 'refactor' },
  test: { bg: 'var(--sticky-orange)', bg2: 'var(--sticky-orange-2)', chip: '#c2410c', label: 'test' },
  security: { bg: '#ffd8a8', bg2: '#fdba74', chip: '#9a3412', label: 'sec' },
};

export function kindStyle(kind: string | undefined): KindStyle {
  return KIND_COLORS[kind || ''] || KIND_COLORS.feature;
}
