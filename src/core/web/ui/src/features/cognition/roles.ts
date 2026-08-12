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

export interface RoleDetail {
  id: string;
  /** Human title from the role definition's frontmatter, e.g. "Architecture & Design". */
  title: string;
  /** Position in the canonical chain; the producer already sorts by it. */
  order: number;
}

interface RolesPayload {
  roles?: string[];
  details?: RoleDetail[];
}

/** Live role list from the producer endpoint, with a loading fallback so
 *  both pickers (new-chat + agent-mode task authoring) share one source. */
export function useRoles(): string[] {
  const { data } = useApiGet<RolesPayload>(['cognition-roles'], '/api/cognition/roles');
  const roles = data?.roles;
  return roles && roles.length > 0 ? roles : ROLE_FALLBACK;
}

/** Roles with their titles, in canonical chain order. Falls back to bare ids so
 *  a picker still renders when the producer is unreachable. */
export function useRoleDetails(): RoleDetail[] {
  const { data } = useApiGet<RolesPayload>(['cognition-roles'], '/api/cognition/roles');
  const details = data?.details;
  if (details && details.length > 0) return details;
  const ids = data?.roles?.length ? data.roles : ROLE_FALLBACK;
  return ids.map((id, i) => ({ id, title: id, order: i }));
}
