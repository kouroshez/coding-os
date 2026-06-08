import { useEffect, useState } from 'react';
import { useApiGet } from '@/lib/hooks';
import type { Adapter } from './ModelPicker';

interface AdaptersPayload {
  adapters: Adapter[];
  default_model: string;
}

/**
 * Live "working…" label for a streaming turn, read per adapter from
 * adapter.yaml::chat_status — NOT hardcoded, so a new adapter (Codex) ships its
 * own vocabulary with zero frontend change. When the agent is running a concrete
 * tool we show that tool's friendly verb (real status: Read → "Reading");
 * otherwise we rotate the adapter's playful idle phrases (our side: working /
 * cooking / pondering …) every few seconds, the way Claude Code does.
 */
export function useChatStatusLabel(model: string, activity: string, active: boolean): string {
  const { data } = useApiGet<AdaptersPayload>(['config-adapters'], '/api/config/adapters');
  const adapters = data?.adapters ?? [];
  const adapter =
    adapters.find((a) => a.models.some((m) => m.id === model)) ??
    adapters.find((a) => a.available) ??
    adapters[0];
  const labels = adapter?.chat_status?.tool_labels ?? {};
  const idle =
    adapter?.chat_status?.idle_phrases && adapter.chat_status.idle_phrases.length > 0
      ? adapter.chat_status.idle_phrases
      : ['working'];

  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), 2600);
    return () => clearInterval(id);
  }, [active]);

  if (activity) {
    const clean = activity.replace(/^mcp__.*?__/, '');
    return labels[activity] ?? labels[clean] ?? clean;
  }
  return idle[tick % idle.length];
}
