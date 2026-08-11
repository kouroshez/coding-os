import type { ClaudeAuth } from "./settings-types";
import { FieldRow, SectionHeader } from "./SettingsPrimitives";

export function ClaudeAuthSection({
  auth,
  onModeChange,
  apiKeyDraft,
  onApiKeyDraftChange,
}: {
  auth: ClaudeAuth;
  onModeChange: (mode: ClaudeAuth["mode"]) => void;
  apiKeyDraft: string | null;
  onApiKeyDraftChange: (v: string | null) => void;
}) {
  const modeButton = (mode: ClaudeAuth["mode"], label: string) => (
    <button
      type="button"
      onClick={() => onModeChange(mode)}
      aria-pressed={auth.mode === mode}
      className={[
        "rounded border px-3 py-1.5 font-mono text-xs transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
        auth.mode === mode
          ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
          : "border-[var(--cos-border)] text-[var(--cos-muted)] hover:border-[var(--cos-text)] hover:text-[var(--cos-text)]",
      ].join(" ")}
    >
      {label}
    </button>
  );

  return (
    <section className="rounded-lg border border-[var(--cos-border)] bg-[var(--cos-panel)] p-5">
      <SectionHeader
        title="Claude Auth"
        desc="How every Claude dispatch (chat + formula) authenticates. Subscription (default) uses the Claude Code CLI's own login — the common case for Pro/Max/Team users. API Key forwards a key you supply here as ANTHROPIC_API_KEY, which takes precedence over the CLI's login for this project."
      />
      <div className="divide-y divide-[var(--cos-border)]">
        <FieldRow label="Auth mode">
          <div className="flex gap-2">
            {modeButton("subscription", "Subscription (OAuth)")}
            {modeButton("api_key", "API Key")}
          </div>
        </FieldRow>
        {auth.mode === "api_key" && (
          <FieldRow label="API key">
            <input
              type="password"
              autoComplete="off"
              value={apiKeyDraft ?? ""}
              onChange={(e) => onApiKeyDraftChange(e.target.value)}
              placeholder={
                auth.api_key_set
                  ? `configured (${auth.api_key_preview}) — leave blank to keep`
                  : "sk-ant-..."
              }
              className="w-72 rounded border border-[var(--cos-border)] bg-[var(--cos-bg)] px-2 py-1.5 font-mono text-xs text-[var(--cos-text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            />
            {auth.api_key_set && (
              <button
                type="button"
                onClick={() => onApiKeyDraftChange("")}
                className="text-[10px] text-[var(--cos-muted)] underline hover:text-[var(--cos-warn)]"
              >
                clear stored key
              </button>
            )}
            {apiKeyDraft === "" && auth.api_key_set && (
              <span className="text-[10px] text-[var(--cos-warn)]">will clear on save</span>
            )}
          </FieldRow>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--cos-muted)]">
        The key is write-only past this form — reads only ever show <code>api_key_set</code> + a
        last-4 preview, never the raw value. Switching back to Subscription does not delete a stored
        key; it just stops using it for this project.
      </p>
    </section>
  );
}
