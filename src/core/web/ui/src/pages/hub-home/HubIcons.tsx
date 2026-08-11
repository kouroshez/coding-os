import { stroke } from './hub-home-shared';

export function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
export function IconFolderSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v3" />
      <circle cx="15.5" cy="15.5" r="3.5" />
      <path d="m21 21-2.5-2.5" />
    </svg>
  );
}
export function IconBroom() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M19 4 8.5 14.5" />
      <path d="m13 9 2 2" />
      <path d="M14 17.5C10 21.5 4.5 19.5 4.5 19.5s-1-5.5 3-9.5l8 8Z" />
    </svg>
  );
}
export function IconRefresh() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
      <path d="M21 4v4h-4" />
      <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
      <path d="M3 20v-4h4" />
    </svg>
  );
}
export function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
export function IconBox() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" {...stroke}>
      <path d="M3.3 7 12 3l8.7 4" />
      <path d="M3.3 7 12 11l8.7-4" />
      <path d="M12 11v10" />
      <path d="M3.3 7v10L12 21" />
      <path d="M20.7 7v10L12 21" />
    </svg>
  );
}

export function FeatureIcon({ name }: { name: 'chat' | 'board' | 'graph' | 'search' }) {
  const props = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', ...stroke };
  switch (name) {
    case 'chat':
      return (
        <svg {...props}><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8A8.5 8.5 0 0 1 12.5 20a8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" /></svg>
      );
    case 'board':
      return (
        <svg {...props}><rect x="3" y="3" width="7" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="11" rx="1.5" /></svg>
      );
    case 'graph':
      return (
        <svg {...props}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8 7.5 16 7.5M7.5 8 12 16M16.5 8 12 16" /></svg>
      );
    case 'search':
      return <IconSearch />;
  }
}

// --------------------------------------------------------------------------
// Subcomponents
// --------------------------------------------------------------------------

