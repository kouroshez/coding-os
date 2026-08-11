// Layout tuning: the ForceAtlas2 time budget and noverlap settings.

export const FA2_BUDGET_MIN_MS = 800;
export const FA2_BUDGET_MAX_MS = 3000;
export const FA2_BUDGET_PER_NODE_MS = 1.2; // measured empirically on Barnes-Hut

export const NOVERLAP_SETTINGS = {
  maxIterations: 30,
  ratio: 1.1,
  // TASK-406: wider margins give the layout more base spacing so the
  // zoom-adaptive sizing has room to breathe at overview ratios.
  margin: 10,
  expansion: 1.08,
};

export function _fa2Budget(nodeCount: number): number {
  return Math.max(
    FA2_BUDGET_MIN_MS,
    Math.min(FA2_BUDGET_MAX_MS, Math.round(nodeCount * FA2_BUDGET_PER_NODE_MS)),
  );
}

