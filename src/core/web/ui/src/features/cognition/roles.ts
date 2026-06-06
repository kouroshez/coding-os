import { useApiGet } from '@/lib/hooks';

// Loading/offline fallback ONLY — the canonical 11 semantic roles. The
// /api/cognition/roles endpoint (derived from thinking_os/agents/*.md) is
// the source of truth; this single list just avoids an empty dropdown on
// first paint and is the one place a role default lives.
export const ROLE_FALLBACK = [
  'researcher',
  'analyst',
  'architect',
  'documenter',
  'implementer',
  'reviewer',
  'debugger',
  'security_auditor',
  'deployer',
  'observer',
  'refactorer',
];

/** Live role list from the producer endpoint, with a loading fallback so
 *  both pickers (new-chat + agent-mode task authoring) share one source. */
export function useRoles(): string[] {
  const { data } = useApiGet<{ roles: string[] }>(['cognition-roles'], '/api/cognition/roles');
  const roles = data?.roles;
  return roles && roles.length > 0 ? roles : ROLE_FALLBACK;
}
