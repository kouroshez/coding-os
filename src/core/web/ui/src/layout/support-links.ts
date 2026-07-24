// Support / community links — single source of truth for the Hub SupportFooter
// and (manually mirrored) the README "Support / Community" section (TASK-372).
// Only real, resolving targets belong here: the repo lives at kouroshez/coding-os
// (verified against the git remote). Payment placeholders were removed rather
// than shipped as 404s — re-add them here once real handles exist.

export interface SupportLink {
  readonly label: string;
  readonly href: string;
}

export const REPO_URL = 'https://github.com/kouroshez/coding-os';

export const SUPPORT_LINKS: readonly SupportLink[] = [
  { label: 'GitHub', href: REPO_URL },
  { label: 'Star on GitHub', href: `${REPO_URL}/stargazers` },
  { label: 'Sponsor', href: 'https://github.com/sponsors/kouroshez' },
];
