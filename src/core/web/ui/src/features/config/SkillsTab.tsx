import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateApiQueries, useApiGet } from '@/lib/hooks';
import { apiPatch } from '@/lib/api-client';
import { CfgButton, ConfigRow, Pill, SectionCard, StateRow, TabIntro } from './shared';

interface SkillRow {
  name: string;
  tier: string;
  domain: string[];
  globs: string | null;
  description?: string;
  extra?: boolean;
  // Producer fields (config_skills): provenance ("core" / "stack:<id>") + disabled
  // let the Hub Enable/Disable a core/stack skill; `stacks` is the installed
  // stacks that use it, powering the grouped-by-stack view.
  provenance?: string;
  disabled?: boolean;
  stacks?: string[];
}

interface InstalledStack {
  id: string;
  label: string;
}

function ProvenanceBadge({ skill }: { skill: SkillRow }) {
  if (skill.extra) return <Pill tone="ok">yours</Pill>;
  const prov = skill.provenance ?? 'core';
  if (prov.startsWith('stack:')) return <Pill tone="muted">{prov.slice('stack:'.length)}</Pill>;
  return <Pill tone="muted">core</Pill>;
}

export function SkillsTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useApiGet<{ skills: SkillRow[]; installed_stacks: InstalledStack[] }>(
    ['config-skills'],
    '/api/config/skills',
  );
  const [pending, setPending] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  if (isLoading) return <StateRow>Loading skills…</StateRow>;
  if (error) return <StateRow>Could not load skills: {error.message}</StateRow>;
  const rows = data?.skills ?? [];
  const installedStacks = data?.installed_stacks ?? [];

  // Core/stack skills ship by default → Enable/Disable via disabled_skills.
  // The PATCH route (set_project_skill) routes by provenance; the UI sends intent.
  const isCoreStack = (s: SkillRow) => {
    const prov = s.provenance ?? 'core';
    return prov === 'core' || prov.startsWith('stack:');
  };
  const toggle = async (skill: SkillRow) => {
    setPending(skill.name);
    try {
      const nextEnabled = isCoreStack(skill) ? !!skill.disabled : !skill.extra;
      await apiPatch(`/api/config/skills/${skill.name}`, { enabled: nextEnabled });
      await invalidateApiQueries(qc, 'config-skills');
    } finally {
      setPending(null);
    }
  };
  const actionVerb = (s: SkillRow) => (s.extra ? 'Remove' : s.disabled ? 'Enable' : 'Disable');
  const actionTone = (s: SkillRow): 'primary' | 'ghost' | 'danger' =>
    s.extra ? 'danger' : s.disabled ? 'primary' : 'ghost';
  // Active = enforced/loaded for this project: shipped by a stack, used by an
  // installed stack, or an explicit extra. A core skill no installed stack uses
  // is idle (its globs never fire here) — it must NOT read as a green "on".
  const isActive = (s: SkillRow) =>
    !!s.extra || (s.provenance ?? '').startsWith('stack:') || (s.stacks?.length ?? 0) > 0;

  const skillRow = (s: SkillRow) => (
    <ConfigRow
      key={s.name}
      title={<span className={s.disabled ? 'text-[var(--cos-faint)]' : undefined}>{s.name}</span>}
      badges={
        <>
          <ProvenanceBadge skill={s} />
          {!s.extra && (
            <span
              className={`text-[10px] font-medium ${
                s.disabled || !isActive(s) ? 'text-[var(--cos-faint)]' : 'text-[var(--cos-ok)]'
              }`}
            >
              {s.disabled ? 'off' : isActive(s) ? 'on' : 'idle'}
            </span>
          )}
        </>
      }
      meta={
        <>
          {s.tier}
          {s.domain.length > 0 && <> · {s.domain.join(', ')}</>}
          {s.globs && (
            <>
              {' · '}
              <span className="font-mono text-[10px]">{s.globs}</span>
            </>
          )}
        </>
      }
      action={
        <CfgButton
          tone={actionTone(s)}
          busy={pending === s.name}
          disabled={pending !== null && pending !== s.name}
          ariaPressed={s.extra ? undefined : !s.disabled}
          onClick={() => void toggle(s)}
          title={`${actionVerb(s)} ${s.name}`}
        >
          {actionVerb(s)}
        </CfgButton>
      }
    />
  );

  const prov = (s: SkillRow) => s.provenance ?? 'core';
  const shippedBy = (sid: string) => rows.filter((s) => s.provenance === `stack:${sid}` && !s.extra);
  const coreActive = rows.filter((s) => prov(s) === 'core' && (s.stacks?.length ?? 0) > 0 && !s.extra);
  const yourSkills = rows.filter((s) => s.extra);
  const moreAvailable = rows.filter((s) => prov(s) === 'core' && (s.stacks?.length ?? 0) === 0 && !s.extra);

  return (
    <>
      <TabIntro>
        The skills active in this project, grouped by the stack that uses them. Skills are glob-gated — the
        agent loads one automatically before editing matching files. Disable one to drop it for this project.
      </TabIntro>

      {installedStacks.map((stack) => {
        const shipped = shippedBy(stack.id);
        if (shipped.length === 0) return null;
        return (
          <SectionCard
            key={stack.id}
            title={`${stack.label} skills`}
            count={shipped.length}
            subtitle="Shipped by this stack."
          >
            {shipped.map(skillRow)}
          </SectionCard>
        );
      })}

      {coreActive.length > 0 && (
        <SectionCard
          title="Core skills · active"
          count={coreActive.length}
          subtitle="Kernel skills your installed stacks rely on."
        >
          {coreActive.map(skillRow)}
        </SectionCard>
      )}

      {yourSkills.length > 0 && (
        <SectionCard title="Your skills" count={yourSkills.length} subtitle="Added beyond the stacks.">
          {yourSkills.map(skillRow)}
        </SectionCard>
      )}

      {moreAvailable.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            aria-expanded={showMore}
            className="mb-3 flex items-center gap-1.5 rounded-lg border border-[var(--cos-border)] px-3 py-1.5 text-[11px] text-[var(--cos-muted)] hover:text-[var(--cos-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
          >
            <ChevronRight
              size={13}
              aria-hidden
              className={`transition-transform ${showMore ? 'rotate-90' : ''}`}
            />
            {showMore ? 'Hide' : 'Show'} {moreAvailable.length} more available core skills
          </button>
          {showMore && (
            <SectionCard
              title="More available"
              count={moreAvailable.length}
              subtitle="Catalog core skills that no installed stack enforces — they stay idle here (their globs never fire). Disable one to drop it from the project entirely."
            >
              {moreAvailable.map(skillRow)}
            </SectionCard>
          )}
        </>
      )}
    </>
  );
}

