import type { PatternRow, RoiData } from './memory-types';

export function roiColor(trend: string): string {
  if (trend === 'improving') return 'var(--cos-ok)';
  if (trend === 'worsening') return 'var(--cos-err)';
  return 'var(--cos-muted)';
}
// Plain-language read-out — the section must answer "is it working?" in words a
// novice gets, and stay honest when there isn't enough history to judge a trend.
// Direct outcome evidence (did surfaced lessons help?) outranks the stumble
// trend once enough votes exist — MIN_VALIDATIONS guards against judging on noise.
export const MIN_VALIDATIONS = 5;

export function hasHelpfulSignal(roi: RoiData | null): roi is RoiData {
  return !!roi && roi.validations_30d >= MIN_VALIDATIONS && roi.helpful_rate_30d !== null;
}
export function roiHeadline(roi: RoiData | null, trend: string, enough: boolean): string {
  if (hasHelpfulSignal(roi)) {
    const pct = Math.round((roi.helpful_rate_30d as number) * 100);
    if (pct >= 60) return `Yes — lessons are holding up (${pct}% rated helpful)`;
    if (pct < 40) return `Lessons aren’t landing (${pct}% rated helpful)`;
    return `Mixed — ${pct}% of surfaced lessons rated helpful`;
  }
  if (!enough) return 'Too early to tell';
  if (trend === 'improving') return 'Yes — fewer stumbles lately';
  if (trend === 'worsening') return 'Stumbles ticked up recently';
  return 'Steady — stumbles aren’t rising';
}
export function roiSentence(roi: RoiData | null, trend: string, enough: boolean): string {
  if (hasHelpfulSignal(roi))
    return `Based on ${roi.validations_30d} validations in the last 30 days — a lesson counts as helpful when its failure did not recur after being surfaced.`;
  if (!enough)
    return 'coding-os needs a few more work sessions before it can tell whether the agent’s stumbles (blocked actions + errors) are trending down.';
  if (trend === 'improving')
    return 'The agent is hitting fewer blocked actions and errors than before — the lessons are paying off.';
  if (trend === 'worsening')
    return 'The agent hit more blocked actions and errors recently — worth a look at what changed.';
  return 'The agent’s blocked actions and errors are holding steady across recent sessions.';
}

// Confidence tier → colour. Meaning, not decoration. (See learning-extraction.md.)
export function tierStyle(tier: string): { bg: string; fg: string } {
  if (tier === 'Promoted') return { bg: 'var(--cos-brand-tint)', fg: 'var(--cos-brand-text)' };
  if (tier === 'Trusted') return { bg: 'var(--cos-ok-tint)', fg: 'var(--cos-ok)' };
  if (tier === 'Fading') return { bg: 'var(--cos-warn-tint)', fg: 'var(--cos-warn)' };
  return { bg: 'var(--cos-overlay)', fg: 'var(--cos-muted)' }; // Forming
}

// 'stat' rows are success-rate baselines (observability) — shown separately,
// never as a learning. Everything else is a belief/lesson.
export function isStat(p: PatternRow): boolean {
  return p.memory_type === 'stat';
}

// Split ANY producer lesson format on the " → " separator: left = situation
// (what happened), right = action (what to do). Covers all 4 shapes —
// "Recurring <kind> (N occurrences): …", "Fixed repeatedly (N occurrences): …",
// "Reverted before: …", and arrow-less ([Breakthrough] …) → whole text, no action.
// Exported for unit testing (the previous regex only matched "Recurring …",
// silently dropping the action line from revert/fix lessons — audit regression).
export function splitLesson(pattern: string): { situation: string; action: string | null } {
  const arrow = pattern.lastIndexOf(' → ');
  if (arrow === -1) return { situation: pattern, action: null };
  const action = pattern.slice(arrow + 3).trim();
  const situation = pattern
    .slice(0, arrow)
    .trim()
    .replace(/^(Recurring [a-z ]+|Fixed repeatedly)\s*\(\d+ occurrences?\):\s*/i, '');
  return { situation: situation || pattern.slice(0, arrow).trim(), action };
}

// Distilled lessons store the sanitized failure samples that justified them.
export function evidenceSamples(p: PatternRow): string[] {
  if (!p.evidence_json) return [];
  try {
    const parsed = JSON.parse(p.evidence_json) as { samples?: unknown };
    if (Array.isArray(parsed.samples)) return parsed.samples.map(String).slice(0, 3);
  } catch {
    /* malformed evidence is not worth an error surface */
  }
  return [];
}

// L1+L2+L3 progressive-disclosure card with 👍/👎 feedback (closes the loop).
