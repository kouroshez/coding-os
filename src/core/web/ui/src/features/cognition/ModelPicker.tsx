import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useApiGet } from "@/lib/hooks";

/**
 * Adapter-grouped chat model picker. Reads /api/config/adapters, which probes
 * each capability at runtime, and shows models grouped UNDER their adapter.
 *
 * An adapter that cannot stream a live turn is NOT "coming soon" — that phrasing
 * described a working dispatcher as vapourware for as long as a yaml string said
 * so. It states which capability is missing and where the adapter IS usable
 * today, so the reader can act instead of wait.
 */

export interface AdapterModel {
  id: string;
  label: string;
  default: boolean;
}
export interface Adapter {
  id: string;
  label: string;
  runtime: string;
  available: boolean;
  installed?: boolean;
  chat_available?: boolean;
  chat_missing?: string;
  chat_remedy?: string;
  dispatch_available?: boolean;
  dispatch_declared?: boolean;
  transcript_available?: boolean;
  capabilities?: string[];
  health?: {
    state: string;
    failure_count: number;
    retry_after_s: number;
    probe_active: boolean;
    reason: string;
  };
  glyph?: string | null;
  color?: string | null;
  efforts?: string[];
  default_effort?: string;
  chat_status?: { tool_labels?: Record<string, string>; idle_phrases?: string[] };
  models: AdapterModel[];
}
interface AdaptersPayload {
  adapters: Adapter[];
  default_model: string;
  count: number;
}

// `available` predates the per-capability probe and still means "can chat";
// read the explicit flag when the server sends it so the two can never disagree.
export function chatReady(a: Adapter): boolean {
  return a.chat_available ?? a.available;
}

/** Where this adapter still earns its place when it cannot stream a live turn. */
export function elsewhere(a: Adapter): string {
  const roles: string[] = [];
  if (a.dispatch_available) roles.push("roles and supervision");
  if (a.transcript_available) roles.push("reading its past sessions");
  return roles.join(" and ");
}

export default function ModelPicker({
  value,
  onChange,
}: {
  /** Selected model id. Empty string = the adapter default. */
  value: string;
  onChange: (modelId: string) => void;
}) {
  const { data } = useApiGet<AdaptersPayload>(["config-adapters"], "/api/config/adapters");
  // Auto option exists ONLY while settings.model_routing.enabled (TASK-318) —
  // producer: routes/settings.py _DEFAULTS (hub-architecture.md § settings contract).
  const { data: settingsData } = useApiGet<{
    settings: { model_routing?: { enabled: boolean; orchestrator_model: string } };
  }>(["settings"], "/api/settings");
  const autoEnabled = settingsData?.settings?.model_routing?.enabled === true;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const adapters = data?.adapters ?? [];
  const allModels = adapters.flatMap((a) => a.models);
  const defaultModel = allModels.find((m) => m.default);
  const effectiveId = value === "auto" && !autoEnabled ? "" : value || defaultModel?.id || "";
  const isAuto = autoEnabled && effectiveId === "auto";
  const selected = allModels.find((m) => m.id === effectiveId);
  const activeAdapter = adapters.find((a) => a.models.some((m) => m.id === effectiveId));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pick = (id: string) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-md border border-[var(--cos-border)] bg-black/20 px-2.5 py-1 text-[11px] text-[var(--cos-text)] hover:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      >
        {activeAdapter?.glyph && (
          <span
            className="font-mono text-[9px]"
            style={activeAdapter.color ? { color: activeAdapter.color } : undefined}
          >
            {activeAdapter.glyph}
          </span>
        )}
        <span className="font-medium">{isAuto ? "Auto" : (selected?.label ?? "default")}</span>
        <ChevronDown size={12} aria-hidden className="text-[var(--cos-muted)]" />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Select chat model"
          className="absolute bottom-full z-50 mb-1 max-h-80 w-64 overflow-auto rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-1 shadow-xl"
        >
          {autoEnabled && (
            <button
              type="button"
              role="option"
              aria-selected={isAuto}
              onClick={() => pick("auto")}
              className="mb-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-[var(--cos-text)] hover:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
            >
              <span className="font-medium">Auto</span>
              <span className="ml-auto text-[10px] text-[var(--cos-muted)]">routed per prompt</span>
              {isAuto && <span className="text-[10px] text-[var(--cos-accent)]">✓</span>}
            </button>
          )}
          {adapters.map((a) => (
            <div key={a.id} className="mb-1 last:mb-0">
              <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-semibold tracking-wide text-[var(--cos-muted)] uppercase">
                {a.glyph && (
                  <span className="font-mono" style={a.color ? { color: a.color } : undefined}>
                    {a.glyph}
                  </span>
                )}
                <span className="truncate">{a.label}</span>
                {!chatReady(a) && (
                  <span className="ml-auto rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] normal-case text-[var(--cos-faint)]">
                    no live chat
                  </span>
                )}
              </div>
              {!chatReady(a) && (
                <p className="px-2 pb-1 text-[10px] leading-relaxed text-[var(--cos-faint)]">
                  {a.chat_remedy
                    ? `Needs ${a.chat_missing} — ${a.chat_remedy}`
                    : `Hub chat streams in-process; ${a.label} has no in-process runtime.`}
                  {elsewhere(a) && (
                    <>
                      {" "}
                      <span className="text-[var(--cos-muted)]">Usable for {elsewhere(a)}.</span>
                    </>
                  )}
                </p>
              )}
              {a.models.map((m) => {
                const isSel = effectiveId === m.id;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={isSel}
                    disabled={!chatReady(a)}
                    onClick={() => pick(m.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-[var(--cos-text)] enabled:hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${isSel ? "bg-[var(--cos-accent)]" : "bg-transparent"}`}
                      aria-hidden
                    />
                    <span className="flex-1 truncate">{m.label}</span>
                    {m.default && (
                      <span className="text-[9px] text-[var(--cos-faint)]">default</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
