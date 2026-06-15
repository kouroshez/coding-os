// Support / community links — single source of truth for the Hub SupportFooter
// and (manually mirrored) the README "Support / Community" section (TASK-372).
// The two GitHub URLs are real; Sponsors / Buy-Me-a-Coffee / crypto are
// placeholders. TODO(TASK-372): replace the three placeholders with real
// handles before public release — grep `TODO(TASK-372)` to find them all.

export interface SupportLink {
  readonly label: string;
  readonly href: string;
}

export const REPO_URL = 'https://github.com/kouroshebra/coding-os';

export const SUPPORT_LINKS: readonly SupportLink[] = [
  { label: 'GitHub', href: REPO_URL },
  { label: 'Star on GitHub', href: `${REPO_URL}/stargazers` },
  // TODO(TASK-372): verify GitHub Sponsors is enabled for this account.
  { label: 'Sponsor', href: 'https://github.com/sponsors/kouroshebra' },
  // TODO(TASK-372): real Buy-Me-a-Coffee handle pending.
  { label: 'Buy me a coffee', href: 'https://www.buymeacoffee.com/TODO-handle' },
  // TODO(TASK-372): real wallet address pending — points at the README section for now.
  { label: 'Support via crypto', href: `${REPO_URL}#support--community` },
];
