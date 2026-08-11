// Shapes served by /api/hub/* (routes/_hub_init.py, _hub_init_routes.py).

export interface PresetItem {
  id: string; label: string; description: string; stacks: string[];
  provenance?: 'core' | 'user';
}
export interface StackItem { id: string; label: string; category: string; language: string }
export interface AdapterItem { id: string; label: string }
export interface ModuleItem { id: string; label: string; kernel: boolean; depends_on: string[] }
export interface ModulesPayload { modules: ModuleItem[]; default_profile: string; default_disabled: string[] }
export interface SkillEntry {
  name: string; tier: string | null; domain: string[];
  description: string; provenance: string; validated: boolean;
}
export interface StackSkillGroups {
  stack: string;
  groups: { required: SkillEntry[]; recommended: SkillEntry[]; optional: SkillEntry[] };
}
export interface ValidatePayload {
  valid: boolean; name: string; auto_named: boolean; target: string;
  templates: string[]; agents: string[]; swimlanes: string[]; conflicts: string[];
}

export interface JobSnapshot { job_id: string; status: string; phase: string; log: string[] }


export interface JobProgress {
  jobId: string;
  phase: string;
  log: string[];
  status: 'running' | 'succeeded' | 'failed' | 'cancelled';
  error: string;
}


export interface ComposerState {
  mode: 'preset' | 'custom';
  preset: string;
  stacks: string[];
  agents: string[];
  extraSkills: string[];
  disabledModules: string[];
  name: string;
  skipName: boolean;
  description: string;
  parentDir: string;
}

// --------------------------------------------------------------------------
// Presentational primitives (tokens + ActionPill vocabulary, no raw hex)
// --------------------------------------------------------------------------

