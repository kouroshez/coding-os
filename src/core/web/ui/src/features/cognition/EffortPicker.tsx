import { useApiGet } from '@/lib/hooks';
import type { Adapter } from './ModelPicker';

/**
 * Reasoning-effort selector, read per adapter from /api/config/adapters
 * (adapter.yaml::efforts). Renders nothing for adapters that declare no effort
 * levels — so the control only appears when the active model's SDK supports it
 * (Claude: low|medium|high|xhigh|max). "default" sends nothing, letting the
 * model pick its own.
 */

interface AdaptersPayload {
  adapters: Adapter[];
  default_model: string;
}

export default function EffortPicker({
  model,
  value,
  onChange,
}: {
  /** The currently selected model id — used to find its adapter's effort levels. */
  model: string;
  value: string;
  onChange: (effort: string) => void;
}) {
  const { data } = useApiGet<AdaptersPayload>(['config-adapters'], '/api/config/adapters');
  const adapters = data?.adapters ?? [];
  const adapter =
    adapters.find((a) => a.models.some((m) => m.id === model)) ??
    adapters.find((a) => a.available) ??
    adapters[0];
  const efforts = adapter?.efforts ?? [];
  if (efforts.length === 0) return null;

  return (
    <label className="flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] bg-black/20 px-2.5 py-1 text-[11px] text-[var(--cos-muted)]">
      <span>effort</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Reasoning effort"
        className="bg-transparent text-[var(--cos-text)] capitalize focus:outline-none"
      >
        <option value="">{adapter?.default_effort ? `default · ${adapter.default_effort}` : 'default'}</option>
        {efforts.map((lv) => (
          <option key={lv} value={lv}>
            {lv}
          </option>
        ))}
      </select>
    </label>
  );
}
