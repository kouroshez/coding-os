import { useState } from 'react';
import { Chip, FieldLabel, Pill } from './shared';
import { FIELD_TIPS, PROTECTED_BRANCH_CHIPS, QUICK_START_PRESETS, isBranchPattern } from './git-tab-data';
import type { GitSettings, GitState } from './git-tab-data';

/** Probe result pills: remote / gh / required CI / pr-ready, plus repo facts. */
export function GitCapabilityStrip({
  state,
  loading,
  error,
}: {
  state: GitState | undefined;
  loading: boolean;
  error: Error | null;
}) {
  return (
    <>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-[var(--cos-faint)]">capability:</span>
        {loading && <Pill tone="muted">checking…</Pill>}
        {!loading && error && !state && <Pill tone="muted">unavailable — git/gh probe failed</Pill>}
        {state && (
          <>
            <Pill tone={state.remote ? 'ok' : 'muted'}>remote {state.remote ? '✓' : '—'}</Pill>
            <Pill tone={state.gh ? 'ok' : 'muted'}>gh {state.gh ? '✓' : '—'}</Pill>
            <Pill tone={state.required_check ? 'ok' : 'muted'}>required CI {state.required_check ? '✓' : '—'}</Pill>
            <Pill tone={state.pr_ok ? 'ok' : 'muted'}>
              {state.pr_ok ? 'pr-ready' : 'PR publish unavailable'}
            </Pill>
          </>
        )}
      </div>

      {state && (state.current_branch || state.remote_url) && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--cos-faint)]">
          {state.current_branch && (
            <span>
              current: <span className="font-mono text-[var(--cos-muted)]">{state.current_branch}</span>
            </span>
          )}
          {state.remote_url && (
            <span>
              remote: <span className="font-mono text-[var(--cos-muted)]">{state.remote_url}</span>
            </span>
          )}
          <span>{state.branches.length} branches</span>
        </div>
      )}
    </>
  );
}

/** One-click preset cards that fill the form below (never the global default). */
export function GitQuickStart({
  isActive,
  onApply,
}: {
  isActive: (apply: GitSettings) => boolean;
  onApply: (apply: GitSettings) => void;
}) {
  return (
    <div className="mb-4">
      <span className="text-xs font-medium text-[var(--cos-muted)]">Quick start</span>
      <p className="mb-2 text-[11px] text-[var(--cos-faint)]">
        One click fills the form below — review it, then Save. A preset never changes the global
        default (which stays Off).
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {QUICK_START_PRESETS.map((preset) => {
          const active = isActive(preset.apply);
          return (
            <button
              key={preset.id}
              type="button"
              aria-pressed={active}
              onClick={() => onApply(preset.apply)}
              className={`rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none ${
                active
                  ? 'border-[var(--cos-accent)] bg-[var(--cos-accent)]/10 hover:bg-[var(--cos-accent)]/15'
                  : 'border-[var(--cos-border)] hover:border-[var(--cos-accent)]'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span className="text-sm font-medium text-[var(--cos-text)]">{preset.label}</span>
                {preset.recommended && (
                  <span className="rounded-full bg-[var(--cos-accent)]/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[var(--cos-accent)]">
                    ★ Recommended
                  </span>
                )}
              </span>
              <span className="mt-1 block text-[11px] leading-relaxed text-[var(--cos-muted)]">
                {preset.blurb}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Protected-branch picker: repo checkbox list, or chips + custom add as fallback. */
export function ProtectedBranchesField({
  selected,
  branches,
  hasBranchList,
  onChange,
}: {
  selected: string[];
  branches: string[];
  hasBranchList: boolean;
  onChange: (next: string[]) => void;
}) {
  const [custom, setCustom] = useState('');
  const isProtected = (branch: string) => selected.includes(branch);
  const toggle = (branch: string, on: boolean) =>
    onChange(on ? [...selected, branch] : selected.filter((x) => x !== branch));
  const addCustom = () => {
    const value = custom.trim();
    if (value && !isProtected(value)) toggle(value, true);
    setCustom('');
  };

  return (
    <div className="block">
      <span className="flex items-center justify-between">
        <FieldLabel label="Protected branches" tip={FIELD_TIPS.protected_branches} />
        <button
          type="button"
          onClick={() => onChange([])}
          disabled={selected.length === 0}
          className="rounded border border-[var(--cos-border)] px-2 py-0.5 text-[10px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none disabled:opacity-40"
        >
          None
        </button>
      </span>
      {hasBranchList ? (
        <div className="mt-1 max-h-40 space-y-1 overflow-auto rounded-md border border-[var(--cos-border)] p-2">
          {branches.map((b) => (
            <label key={b} className="flex items-center gap-2 text-sm text-[var(--cos-text)]">
              <input
                type="checkbox"
                checked={isProtected(b)}
                onChange={(e) => toggle(b, e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--cos-accent)] focus-visible:ring-2"
              />
              <span className="font-mono text-[12px]">{b}</span>
            </label>
          ))}
          {selected
            .filter((b) => !branches.includes(b))
            .map((b) => (
              <label key={b} className="flex items-center gap-2 text-sm text-[var(--cos-faint)]">
                <input
                  type="checkbox"
                  checked
                  onChange={() => toggle(b, false)}
                  className="h-3.5 w-3.5 accent-[var(--cos-accent)] focus-visible:ring-2"
                />
                <span className="font-mono text-[12px]">
                  {b} {isBranchPattern(b) ? '(pattern)' : '(not in repo)'}
                </span>
              </label>
            ))}
        </div>
      ) : (
        // Fallback when no branch list — common toggle chips + custom add.
        <span className="mt-1 flex flex-wrap gap-1.5">
          {[...PROTECTED_BRANCH_CHIPS, ...selected.filter((b) => !PROTECTED_BRANCH_CHIPS.includes(b))].map((b) => (
            <Chip
              key={b}
              active={isProtected(b)}
              ariaLabel={`${isProtected(b) ? 'Unprotect' : 'Protect'} ${b}`}
              onClick={() => toggle(b, !isProtected(b))}
            >
              {b}
            </Chip>
          ))}
        </span>
      )}
      <span className="mt-2 flex gap-1.5">
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addCustom();
            }
          }}
          placeholder="add a branch…"
          aria-label="Add protected branch"
          className="flex-1 rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)]/40 px-2.5 py-1 text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none"
        />
        <button
          type="button"
          onClick={addCustom}
          disabled={!custom.trim()}
          className="rounded-md border border-[var(--cos-border)] px-2.5 py-1 text-xs text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)] focus:outline-none disabled:opacity-40"
        >
          Add
        </button>
      </span>
      <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
        {selected.length === 0 ? 'None — no protected branches.' : `Human-only: ${selected.join(', ')}`}
      </span>
      <span className="mt-1 block text-[11px] text-[var(--cos-faint)]">
        Exact names and patterns are enforced; <span className="font-mono">release/*</span> covers{' '}
        <span className="font-mono">release/v1</span>, not{' '}
        <span className="font-mono">release-candidate</span>.
      </span>
    </div>
  );
}
