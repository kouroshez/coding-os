import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import { apiGet, apiPost } from '@/lib/api-client';
import { slugifyProjectName } from '../hub-home/hub-home-shared';
import type {
  AdapterItem,
  ComposerState,
  JobProgress,
  JobSnapshot,
  ModulesPayload,
  PresetItem,
  SkillEntry,
  StackItem,
  StackSkillGroups,
  ValidatePayload,
} from './wizard-types';
import { CORE_SKILLS, NAME_RE, forgetJob, readParkedJob, rememberJob } from './wizard-constants';

// Every wizard fetch, derivation and mutation. The shell below stays
// render-only so a producer change lands in exactly one module.
export function useWizardComposer(
  suggestions: string[],
  onClose: () => void,
  onCreated: (slug: string) => void,
) {
  const [state, setState] = useState<ComposerState>({
    mode: 'preset', preset: '', stacks: [], agents: ['claude'],
    extraSkills: [], disabledModules: [], name: '', skipName: false, description: '',
    parentDir: suggestions[0] ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [skillGroups, setSkillGroups] = useState<StackSkillGroups[]>([]);
  const [validation, setValidation] = useState<ValidatePayload | null>(null);
  const [validating, setValidating] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [presetQuery, setPresetQuery] = useState('');
  const [job, setJob] = useState<JobProgress | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: presetsData } = useApiGet<{ presets: PresetItem[] }>(['hub-presets'], '/api/hub/presets');
  const { data: stacksData } = useApiGet<{ stacks: StackItem[] }>(['hub-stacks'], '/api/hub/stacks');
  const { data: adaptersData } = useApiGet<{ adapters: AdapterItem[] }>(['hub-adapters'], '/api/hub/adapters');
  const { data: catalogData } = useApiGet<{ skills: SkillEntry[] }>(['hub-skills'], '/api/hub/skills');
  const { data: modulesData } = useApiGet<ModulesPayload>(['hub-modules'], '/api/hub/modules');
  // Seed the chips with the profile a hand-typed `cos init` would apply, so the
  // toggles show the real starting point instead of an all-on fiction. Once the
  // user touches a chip their choice wins (the create call sends --profile full).
  const modulesSeeded = useRef(false);
  useEffect(() => {
    const seed = modulesData?.default_disabled;
    if (!seed || modulesSeeded.current) return;
    modulesSeeded.current = true;
    setState((s) => (s.disabledModules.length ? s : { ...s, disabledModules: [...seed] }));
  }, [modulesData]);

  const selectedStacks = useMemo(() => {
    if (state.mode === 'preset') {
      return presetsData?.presets.find((p) => p.id === state.preset)?.stacks ?? [];
    }
    return state.stacks;
  }, [state.mode, state.preset, state.stacks, presetsData]);
  const stacksSig = selectedStacks.join(',');

  const stacksByLanguage = useMemo(() => {
    const groups = new Map<string, StackItem[]>();
    for (const s of stacksData?.stacks ?? []) {
      const lang = s.language || 'other';
      groups.set(lang, [...(groups.get(lang) ?? []), s]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [stacksData]);

  const filteredPresets = useMemo(() => {
    const q = presetQuery.trim().toLowerCase();
    const all = presetsData?.presets ?? [];
    if (!q) return all;
    return all.filter(
      (p) => p.label.toLowerCase().includes(q)
        || p.description.toLowerCase().includes(q)
        || p.stacks.some((s) => s.toLowerCase().includes(q)),
    );
  }, [presetsData, presetQuery]);

  // Skill groups for the selected stacks + auto-seed recommended core skills
  // into extra_skills (they are NOT auto-installed by the scaffold — only the
  // stack's own skill dirs are linked, so the curated core companions need to
  // ride the --skills flag). Re-seeds whenever the stack set changes; user
  // toggles persist within a stack set.
  useEffect(() => {
    if (selectedStacks.length === 0) { setSkillGroups([]); setState((s) => ({ ...s, extraSkills: [] })); return; }
    let cancelled = false;
    void Promise.all(
      selectedStacks.map((id) =>
        apiGet<StackSkillGroups>(`/api/hub/stacks/${encodeURIComponent(id)}/skills`)
          .then(([data]) => data)
          .catch(() => null)),
    ).then((results) => {
      if (cancelled) return;
      const groups = results.filter(Boolean) as StackSkillGroups[];
      setSkillGroups(groups);
      const seed = new Set<string>();
      for (const g of groups) {
        for (const e of g.groups.recommended) {
          if (e.provenance === 'core' && e.validated) seed.add(e.name);
        }
      }
      setState((s) => ({ ...s, extraSkills: [...seed] }));
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stacksSig]);

  const runValidate = useCallback(async () => {
    if (!state.parentDir.trim()) { setValidation(null); return; }
    setValidating(true);
    setError(null);
    try {
      const [data] = await apiPost<ValidatePayload>('/api/hub/registry/validate-init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agents: state.agents,
        disabled_modules: state.disabledModules,
      });
      setValidation(data);
    } catch (err) {
      setValidation(null);
      setError(err instanceof Error ? err.message : 'validation failed');
    } finally {
      setValidating(false);
    }
  }, [state.parentDir, state.skipName, state.name, state.mode, state.stacks, state.preset, state.agents, state.disabledModules]);

  // Debounced live preview — re-validates whenever a relevant choice changes.
  useEffect(() => {
    const t = setTimeout(() => { void runValidate(); }, 350);
    return () => clearTimeout(t);
  }, [runValidate]);

  const recommendedChips = useMemo(() => {
    const seen = new Set<string>();
    const out: SkillEntry[] = [];
    for (const g of skillGroups) {
      for (const e of g.groups.recommended) {
        if (e.provenance === 'core' && e.validated && !seen.has(e.name)) { seen.add(e.name); out.push(e); }
      }
    }
    return out;
  }, [skillGroups]);

  const requiredEntries = useMemo(() => {
    const seen = new Set<string>();
    const out: SkillEntry[] = [];
    for (const g of skillGroups) {
      for (const e of g.groups.required) {
        if (!seen.has(e.name)) { seen.add(e.name); out.push(e); }
      }
    }
    return out;
  }, [skillGroups]);

  const optionalSkills = useMemo(() => {
    const installed = new Set(
      skillGroups.flatMap((g) => [...g.groups.required, ...g.groups.recommended]).map((e) => e.name),
    );
    return (catalogData?.skills ?? []).filter(
      (s) => s.provenance === 'core' && s.validated && !installed.has(s.name) && !CORE_SKILLS.includes(s.name),
    );
  }, [catalogData, skillGroups]);

  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  const moduleCatalog = modulesData?.modules ?? [];
  const isModuleOn = (id: string) => !state.disabledModules.includes(id);
  // Toggle a module, keeping the dependency graph valid (tasks needs docs):
  // disabling a module also disables its dependents; enabling re-enables deps.
  const toggleModule = (id: string) => setState((s) => {
    const disabled = new Set(s.disabledModules);
    if (disabled.has(id)) {
      disabled.delete(id);
      for (const dep of moduleCatalog.find((m) => m.id === id)?.depends_on ?? []) disabled.delete(dep);
    } else {
      disabled.add(id);
      for (const m of moduleCatalog) if (m.depends_on.includes(id)) disabled.add(m.id);
    }
    return { ...s, disabledModules: [...disabled] };
  });

  const slug = slugifyProjectName(state.name);
  // Empty name is fine — the backend assigns a temp slug (auto_named). Only a
  // non-empty name has to be a valid slug.
  const nameOk = state.skipName || slug === '' || NAME_RE.test(slug);
  const choiceOk = state.mode === 'preset' ? state.preset !== '' : true;
  const canCreate = Boolean(validation?.valid) && state.parentDir.trim() !== ''
    && nameOk && choiceOk && state.agents.length > 0 && !busy;

  const create = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [started] = await apiPost<{ job_id: string; name: string }>('/api/hub/registry/init', {
        name: state.skipName ? '' : slugifyProjectName(state.name),
        parent_dir: state.parentDir.trim(),
        stacks: state.mode === 'custom' ? state.stacks : [],
        preset: state.mode === 'preset' ? state.preset : '',
        agents: state.agents,
        description: state.description,
        extra_skills: state.extraSkills,
        disabled_modules: state.disabledModules,
        background: true,
      });
      rememberJob(started.job_id);
      setJob({ jobId: started.job_id, phase: 'validate', log: [], status: 'running', error: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'create failed');
      setBusy(false);
    }
  }, [state]);

  // A create outlives the tab: the job id is server-side state, so park it in
  // sessionStorage and re-attach on mount. Without this a reload during a
  // 30-second scaffold silently orphans the progress view.
  useEffect(() => {
    const parked = readParkedJob();
    if (!parked) return;
    apiGet<JobSnapshot>(`/api/hub/init-jobs/${encodeURIComponent(parked)}`)
      .then(([snapshot]) => {
        // HubHome opens this modal whenever a job is parked, so a finished or
        // vanished job has to close it again — otherwise the user faces an
        // empty "Create a new project" dialog they never asked for.
        if (!snapshot || snapshot.status !== 'running') { forgetJob(); onClose(); return; }
        setBusy(true);
        setJob({
          jobId: parked,
          phase: snapshot.phase,
          log: snapshot.log,
          status: 'running',
          error: '',
        });
      })
      .catch(() => { forgetJob(); onClose(); });
  }, []);

  // Job progress stream (TASK-362): replay + follow; reconnects after refresh.
  useEffect(() => {
    if (!job || job.status !== 'running') return;
    const source = new EventSource(`/api/hub/init-jobs/${encodeURIComponent(job.jobId)}/events`);
    const append = (line: string) =>
      setJob((j) => (j ? { ...j, log: [...j.log.slice(-199), line] } : j));
    source.addEventListener('log', (e) => append((JSON.parse((e as MessageEvent).data) as { line: string }).line));
    source.addEventListener('phase', (e) =>
      setJob((j) => (j ? { ...j, phase: (JSON.parse((e as MessageEvent).data) as { phase: string }).phase } : j)));
    const terminal = (status: JobProgress['status']) => (e: Event) => {
      const payload = JSON.parse((e as MessageEvent).data) as { error?: string; result?: { slug?: string } };
      source.close();
      forgetJob();
      setBusy(false);
      if (status === 'succeeded') { onCreated(payload.result?.slug ?? ''); return; }
      setJob((j) => (j ? { ...j, status, error: payload.error ?? '' } : j));
      if (status === 'failed') setError(payload.error || 'init failed');
    };
    source.addEventListener('succeeded', terminal('succeeded'));
    source.addEventListener('failed', terminal('failed'));
    source.addEventListener('cancelled', terminal('cancelled'));
    source.onerror = () => { /* EventSource auto-reconnects; job state is server-side */ };
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.jobId, job?.status]);

  const cancelJob = useCallback(async () => {
    if (!job) return;
    try {
      await apiPost(`/api/hub/init-jobs/${encodeURIComponent(job.jobId)}/cancel`, {});
    } catch {
      // terminal event (or 404) resolves the UI state either way
    }
  }, [job]);


  return {
    adaptersData,
    advancedOpen,
    busy,
    canCreate,
    cancelJob,
    create,
    error,
    filteredPresets,
    isModuleOn,
    job,
    moduleCatalog,
    modulesData,
    nameOk,
    optionalSkills,
    presetQuery,
    presetsData,
    recommendedChips,
    requiredEntries,
    selectedStacks,
    setAdvancedOpen,
    setError,
    setJob,
    setPresetQuery,
    setState,
    slug,
    stacksByLanguage,
    state,
    toggle,
    toggleModule,
    validating,
    validation,
  };
}
