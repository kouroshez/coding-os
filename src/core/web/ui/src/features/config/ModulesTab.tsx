import { useState } from 'react';
import { Lock } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';
import { Pill, StateRow, TabIntro, Table } from './shared';

interface ModuleOwned {
  hooks: string[];
  tools: string[];
  skills: string[];
  commands: string[];
  rules: string[];
}

interface ModuleRow {
  id: string;
  label: string;
  hint?: string;
  kernel: boolean;
  enabled: boolean;
  depends_on: string[];
  depends_on_reason?: string;
  hooks: number;
  tools: number;
  skills: number;
  commands: number;
  rules: number;
  owned?: ModuleOwned;
}

interface DriftRow {
  id: string;
  severity: string;
  message: string;
}

// Named identities of everything a module owns — the "see the blast radius"
// detail the Owns cell exposes on hover so a disable is never a blind leap.
function ownedTitle(m: ModuleRow): string {
  const o = m.owned;
  if (!o) return '';
  return (
    [
      o.hooks.length ? `hooks: ${o.hooks.join(', ')}` : '',
      o.tools.length ? `tools: ${o.tools.join(', ')}` : '',
      o.skills.length ? `skills: ${o.skills.join(', ')}` : '',
      o.commands.length ? `commands: ${o.commands.join(', ')}` : '',
      o.rules.length ? `rules: ${o.rules.join(', ')}` : '',
    ]
      .filter(Boolean)
      .join('\n') || 'no owned artifacts'
  );
}

export function ModulesTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ modules: ModuleRow[] }>(
    ['settings-modules'],
    '/api/settings/modules',
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  // A Hub toggle can strand a skill/command symlink or corrupt state; surface
  // the same `cos doctor` drift checks so the UI that caused it shows it (HUB-PB2).
  const { data: driftData } = useApiGet<{ drift: DriftRow[]; ok: boolean }>(
    ['settings-modules-drift'],
    '/api/settings/modules/drift',
  );

  if (isLoading) return <StateRow>Loading modules…</StateRow>;
  if (error) return <StateRow>Could not load modules: {error.message}</StateRow>;
  const rows = data?.modules ?? [];
  const drift = driftData?.drift ?? [];

  // Reverse dependency edges, derived from the rows the API already returns —
  // so the table SHOWS "what depends on this" and greys out a disable the
  // backend would refuse, instead of surfacing a raw refusal only after a click.
  const dependentsOf = (id: string) => rows.filter((r) => r.depends_on.includes(id)).map((r) => r.id);
  const enabledDependentsOf = (id: string) =>
    rows.filter((r) => r.enabled && r.depends_on.includes(id)).map((r) => r.id);
  const disabledDepsOf = (m: ModuleRow) =>
    m.depends_on.filter((d) => rows.some((r) => r.id === d && !r.enabled));

  const toggle = async (row: ModuleRow) => {
    setBusyId(row.id);
    setToggleError(null);
    setNotes([]);
    try {
      const [resp] = await apiPatch<{ regenerated?: string[] }>(
        `/api/settings/modules/${encodeURIComponent(row.id)}`,
        { enabled: !row.enabled },
      );
      setNotes(resp?.regenerated ?? []);
      await invalidateApiQueries(qc, '/api/settings/modules');
      await invalidateApiQueries(qc, '/api/settings/modules/drift');
    } catch (err) {
      setToggleError(err instanceof Error ? err.message : 'toggle failed');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <TabIntro>
        Subsystem modules for this project. The kernel is always on; disabling a module gates its
        MCP tools and self-skips its hooks (re-enable any time — state lives in
        .coding-os/subsystems-state.json).
      </TabIntro>
      {toggleError && (
        <p role="alert" className="mb-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-400">
          {toggleError}
        </p>
      )}
      {drift.length > 0 && (
        <div role="alert" className="mb-3 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-300">
          <div className="font-medium">⚠️ Module drift detected ({drift.length}) — a disabled module left an artifact behind</div>
          <ul className="mt-1 list-disc pl-4 text-amber-200/90">
            {drift.map((d) => (
              <li key={d.id}>
                <span className="font-mono">{d.id}</span>: {d.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {notes.length > 0 && (
        <div className="mb-3 rounded border border-[var(--cos-border)] bg-white/[0.02] p-2 text-xs text-[var(--cos-muted)]">
          <div className="flex items-center justify-between">
            <span className="font-medium text-[var(--cos-text)]">Applied ({notes.length})</span>
            <button
              type="button"
              onClick={() => setNotes([])}
              className="text-[10px] text-[var(--cos-faint)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
            >
              dismiss
            </button>
          </div>
          <ul className="mt-1 list-disc pl-4">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      <Table head={['Module', 'State', 'Owns', 'Depends on', 'Required by', '']}>
        {rows.map((m) => {
          const dependents = dependentsOf(m.id);
          const blockedBy = enabledDependentsOf(m.id);
          const missingDeps = disabledDepsOf(m);
          const disableBlocked = m.enabled && blockedBy.length > 0;
          const enableBlocked = !m.enabled && missingDeps.length > 0;
          const blockedReason = disableBlocked
            ? `Required by ${blockedBy.join(', ')} — disable ${blockedBy.length > 1 ? 'them' : 'it'} first`
            : enableBlocked
              ? `Needs ${missingDeps.join(', ')} — enable ${missingDeps.length > 1 ? 'them' : 'it'} first`
              : undefined;
          return (
            <tr key={m.id} className="border-b border-[var(--cos-border)] last:border-0 hover:bg-white/[0.02]">
              <td className="px-3 py-2">
                <div className="font-medium text-[var(--cos-text)]">{m.id}</div>
                <div className="text-[10px] text-[var(--cos-faint)]">{m.label}</div>
                {m.hint && (
                  <div className="mt-0.5 max-w-md text-[10px] leading-snug text-[var(--cos-muted)]">{m.hint}</div>
                )}
              </td>
              <td className="px-3 py-2">
                {m.kernel ? (
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--cos-accent)]/40 bg-[var(--cos-accent)]/10 px-2.5 py-0.5 text-[10px] font-medium text-[var(--cos-accent)]">
                    <Lock size={11} aria-hidden />
                    kernel · locked
                  </span>
                ) : (
                  <Pill tone={m.enabled ? 'ok' : 'muted'}>{m.enabled ? 'enabled' : 'disabled'}</Pill>
                )}
              </td>
              <td className="px-3 py-2 text-[var(--cos-muted)]">
                <span title={ownedTitle(m)} className="cursor-help">
                  {m.hooks} hooks · {m.tools} tools · {m.skills} skills · {m.commands} commands ·{' '}
                  {m.rules} rules
                </span>
              </td>
              <td className="px-3 py-2 text-[var(--cos-faint)]">
                {m.depends_on.join(', ') || '—'}
                {m.depends_on_reason && (
                  <div className="mt-0.5 max-w-xs text-[10px] italic leading-snug text-[var(--cos-muted)]">
                    {m.depends_on_reason}
                  </div>
                )}
              </td>
              <td className="px-3 py-2 text-[var(--cos-faint)]">{dependents.join(', ') || '—'}</td>
              <td className="px-3 py-2 text-right">
                {!m.kernel && (
                  <>
                    <button
                      type="button"
                      data-testid={`module-toggle-${m.id}`}
                      onClick={() => void toggle(m)}
                      disabled={busyId !== null || disableBlocked || enableBlocked}
                      title={blockedReason}
                      aria-pressed={m.enabled}
                      aria-disabled={disableBlocked || enableBlocked}
                      className="rounded border border-[var(--cos-border)] px-2.5 py-1 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] disabled:opacity-40"
                    >
                      {busyId === m.id ? '…' : m.enabled ? 'Disable' : 'Enable'}
                    </button>
                    {blockedReason && (
                      <div
                        role="note"
                        className="mt-1 max-w-[16rem] text-left text-[10px] leading-snug text-[var(--cos-faint)]"
                      >
                        {blockedReason}
                      </div>
                    )}
                  </>
                )}
              </td>
            </tr>
          );
        })}
      </Table>
    </>
  );
}

