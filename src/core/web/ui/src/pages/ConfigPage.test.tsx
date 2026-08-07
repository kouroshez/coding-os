import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useApiGet: (_key: unknown, path: string) => {
    const map: Record<string, unknown> = {
      "/api/config/stacks": {
        available: [
          {
            id: "meta",
            label: "Meta",
            category: "meta",
            primary_skill: "graph-explorer",
            installed: true,
          },
        ],
        installed: ["meta"],
      },
      "/api/config/skills": {
        skills: [
          {
            name: "clean-code",
            tier: "universal",
            domain: ["all"],
            globs: "**/*",
            provenance: "core",
            stacks: ["meta"],
          },
        ],
        installed_stacks: [{ id: "meta", label: "Meta" }],
      },
      "/api/config/mcp": {
        servers: [{ name: "coding-os", command: "cos", args: ["server-start"], managed: true }],
      },
      "/api/config/mcp/catalog": {
        servers: [
          {
            id: "fetch",
            name: "Fetch",
            description: "Fetch a URL.",
            command: "uvx",
            args: ["mcp-server-fetch"],
            installed: false,
          },
        ],
      },
      "/api/config/adapters": {
        adapters: [
          {
            id: "claude",
            label: "Anthropic Claude Code",
            runtime: "in_process",
            available: true,
            installed: true,
            dispatch_declared: true,
            dispatch_available: true,
            capabilities: ["dispatch"],
            health: {
              state: "cooling_down",
              failure_count: 1,
              retry_after_s: 42,
              probe_active: false,
              reason: "usage limit",
            },
            glyph: "Cl",
            models: [{ id: "claude-opus-4-8", label: "Opus 4.8", default: true }],
            mcp_config_paths: [".mcp.json"],
          },
          {
            id: "codex",
            label: "OpenAI Codex CLI",
            runtime: "roadmap",
            available: false,
            installed: false,
            glyph: "Cx",
            models: [],
            mcp_config_paths: [".codex/config.toml"],
          },
        ],
        default_model: "claude-opus-4-8",
      },
      "/api/hooks/list": {
        hooks: [{ name: "branch-guard", event: "PreToolUse", category: "safety", phase: "1" }],
      },
      "/api/settings/modules": {
        modules: [
          {
            id: "kernel",
            label: "Kernel",
            kernel: true,
            enabled: true,
            depends_on: [],
            hooks: 6,
            tools: 0,
            skills: 0,
            commands: 0,
            rules: 0,
            owned: { hooks: [], tools: [], skills: [], commands: [], rules: [] },
          },
          {
            id: "docs",
            label: "Docs system",
            hint: "Enable for SSOT doc search.",
            kernel: false,
            enabled: true,
            depends_on: [],
            hooks: 6,
            tools: 1,
            skills: 0,
            commands: 0,
            rules: 0,
            owned: { hooks: [], tools: ["cos_doc_*"], skills: [], commands: [], rules: [] },
          },
          {
            id: "tasks",
            label: "Task system",
            hint: "Enable for the Scrumban board.",
            kernel: false,
            enabled: true,
            depends_on: ["docs"],
            depends_on_reason: "Enforcement-locality: docs owns the doc-anchor gate.",
            hooks: 9,
            tools: 2,
            skills: 1,
            commands: 4,
            rules: 0,
            owned: {
              hooks: [],
              tools: [],
              skills: ["task-driver"],
              commands: ["board", "daily", "retro", "task"],
              rules: [],
            },
          },
        ],
      },
      "/api/settings": {
        settings: {
          git_settings: {
            enabled: false,
            integration_branch: "main",
            protected_branches: ["production"],
            autonomy_level: "draft",
          },
        },
      },
      "/api/settings/git-state": {
        remote: false,
        gh: false,
        required_check: false,
        pr_ok: false,
        missing: [],
        branches: [],
        current_branch: "main",
        remote_url: "",
      },
    };
    return { data: map[path] ?? null, isLoading: false, error: null };
  },
  invalidateApiQueries: vi.fn(),
}));

const apiPatch = vi.fn().mockResolvedValue([{ regenerated: ["AGENTS.md regenerated"] }]);
const apiDelete = vi.fn().mockResolvedValue([{ adapter: "claude", cleared: true }]);
vi.mock("@/lib/api-client", () => ({
  apiPatch: (...args: unknown[]) => apiPatch(...args),
  apiDelete: (...args: unknown[]) => apiDelete(...args),
  apiPost: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({}),
}));

import ConfigPage from "./ConfigPage";

function renderConfig(initial = "/p/demo/config") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ConfigPage />
    </MemoryRouter>,
  );
}

describe("ConfigPage", () => {
  it("defaults to the Stacks tab and shows installed status", () => {
    renderConfig();
    expect(screen.getByRole("tab", { name: "Stacks" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Meta")).toBeInTheDocument();
    expect(screen.getByText("Installed")).toBeInTheDocument();
  });

  it("switches to the Skills tab on click", () => {
    renderConfig();
    fireEvent.click(screen.getByRole("tab", { name: "Skills" }));
    expect(screen.getByText("clean-code")).toBeInTheDocument();
  });

  it("opens directly to the Hooks tab from ?tab=hooks", () => {
    renderConfig("/p/demo/config?tab=hooks");
    expect(screen.getByText("branch-guard")).toBeInTheDocument();
  });

  it("opens the Adapters tab: installed adapter with MCP wiring, then reveals addable ones", () => {
    renderConfig("/p/demo/config?tab=adapters");
    expect(screen.getByText("Anthropic Claude Code")).toBeInTheDocument();
    expect(screen.getByText("in_process")).toBeInTheDocument();
    expect(screen.getByText(".mcp.json")).toBeInTheDocument();
    expect(screen.getByText(/retry in 42s/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry now" }));
    expect(apiDelete).toHaveBeenCalledWith("/api/config/adapters/claude/health");
    // codex is declared but not installed → hidden until Add adapter is opened.
    expect(screen.queryByText("OpenAI Codex CLI")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add adapter" }));
    expect(screen.getByText("OpenAI Codex CLI")).toBeInTheDocument();
    expect(screen.getByText(".codex/config.toml")).toBeInTheDocument();
  });
});

describe("ModulesTab (TASK-354)", () => {
  it("kernel renders locked without a toggle; non-kernel toggles via PATCH", async () => {
    renderConfig("/p/demo/config?tab=modules");
    expect(screen.getByText("kernel · locked")).toBeInTheDocument();
    expect(screen.queryByTestId("module-toggle-kernel")).toBeNull();
    const toggle = screen.getByTestId("module-toggle-tasks");
    fireEvent.click(toggle);
    expect(apiPatch).toHaveBeenCalledWith("/api/settings/modules/tasks", { enabled: false });
  });

  it("surfaces the per-module hint for discovery", () => {
    renderConfig("/p/demo/config?tab=modules");
    expect(screen.getByText("Enable for the Scrumban board.")).toBeInTheDocument();
  });

  it("shows reverse dependencies and pre-empts disabling a depended-on module", () => {
    renderConfig("/p/demo/config?tab=modules");
    // docs is required by tasks → its Disable button is greyed out with a reason,
    // instead of throwing a raw refusal only after the click.
    const docsToggle = screen.getByTestId("module-toggle-docs");
    expect(docsToggle).toBeDisabled();
    expect(docsToggle.getAttribute("title")).toMatch(/tasks/);
    // tasks has no dependents → its toggle stays actionable.
    expect(screen.getByTestId("module-toggle-tasks")).not.toBeDisabled();
  });

  it("surfaces the module skills count the producer emits", () => {
    renderConfig("/p/demo/config?tab=modules");
    expect(screen.getByText(/1 skills/)).toBeInTheDocument();
  });

  it("surfaces the dependency rationale and the commands count (TASK-814)", () => {
    renderConfig("/p/demo/config?tab=modules");
    expect(screen.getByText(/Enforcement-locality/)).toBeInTheDocument();
    expect(screen.getByText(/4 commands/)).toBeInTheDocument();
  });

  it("shows the cascade regenerated notes after a successful toggle", async () => {
    renderConfig("/p/demo/config?tab=modules");
    fireEvent.click(screen.getByTestId("module-toggle-tasks"));
    expect(await screen.findByText("AGENTS.md regenerated")).toBeInTheDocument();
  });
});

describe("GitTab (TASK-552)", () => {
  it("renders the full editable tab plus a trunk caution for the meta-repo (slug coding-os)", () => {
    renderConfig("/p/coding-os/config?tab=git");
    // The configurator is NOT hidden on coding-os anymore — the full tab renders.
    expect(screen.getByRole("checkbox", { name: "Enable pr-mode" })).toBeInTheDocument();
    expect(screen.getByText("Team + GitHub CI")).toBeInTheDocument();
    // ...with one caution that enabling here flips the mother repo off trunk.
    expect(screen.getByText(/viewing coding-os, the meta-repo/)).toBeInTheDocument();
    // Meta framing now lives ONLY in that amber caution — the intro/tooltip no longer leak it (TASK-560).
    expect(screen.queryByText(/coding-os itself/)).toBeNull();
  });

  it("offers quick-start presets and per-field info controls on a consumer project", () => {
    renderConfig("/p/demo/config?tab=git");
    expect(screen.getByRole("checkbox", { name: "Enable pr-mode" })).toBeInTheDocument();
    expect(screen.getByText("Team + GitHub CI")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What is Integration branch?" })).toBeInTheDocument();
    expect(screen.getByText(/shared-tree edits can still happen/)).toBeInTheDocument();
    expect(screen.getByText(/Exact names and patterns are enforced/)).toBeInTheDocument();
    expect(
      screen.getByText(/Draft, auto-merge, and autonomous publish through GitHub/),
    ).toBeInTheDocument();
    expect(screen.getByText("PR publish unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Protect release/*" })).toBeInTheDocument();
    // A consumer must never see meta-repo framing (TASK-560): no amber caution, no "coding-os itself" leak.
    expect(screen.queryByText(/viewing coding-os, the meta-repo/)).toBeNull();
    expect(screen.queryByText(/coding-os itself/)).toBeNull();
  });

  it("highlights the preset that matches the form, not the Recommended one (TASK-555)", () => {
    renderConfig("/p/demo/config?tab=git");
    // Saved default (enabled=false) matches no preset → Recommended is NOT pre-selected.
    const recommended = screen.getByRole("button", { name: /Team \+ GitHub CI/ });
    expect(recommended).toHaveAttribute("aria-pressed", "false");
    // Clicking a preset fills the form → only that card reads as active/selected.
    const mainDevProd = screen.getByRole("button", { name: /main → dev → prod/ });
    fireEvent.click(mainDevProd);
    expect(mainDevProd).toHaveAttribute("aria-pressed", "true");
    expect(recommended).toHaveAttribute("aria-pressed", "false");
  });

  it('the None control clears protected branches and reads "None"', () => {
    renderConfig("/p/demo/config?tab=git");
    expect(screen.getByText("Human-only: production")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "None" }));
    expect(screen.getByText("None — no protected branches.")).toBeInTheDocument();
  });

  it("Save sends the unchanged PATCH payload shape", () => {
    renderConfig("/p/demo/config?tab=git");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(apiPatch).toHaveBeenCalledWith("/api/settings", {
      git_settings: {
        enabled: false,
        integration_branch: "main",
        protected_branches: ["production"],
        autonomy_level: "draft",
      },
    });
  });

  it("hard-blocks enabling pr-mode on the meta-repo (H5)", () => {
    renderConfig("/p/coding-os/config?tab=git");
    expect(screen.getByRole("checkbox", { name: "Enable pr-mode" })).toBeDisabled();
  });

  it("gates the first enable behind an explicit confirm step (H5)", () => {
    renderConfig("/p/demo/config?tab=git");
    apiPatch.mockClear();
    fireEvent.click(screen.getByRole("checkbox", { name: "Enable pr-mode" }));
    fireEvent.click(screen.getByRole("button", { name: "Enable pr-mode…" }));
    // First click only opens the confirm — it must NOT PATCH yet.
    expect(apiPatch).not.toHaveBeenCalled();
    expect(
      screen.getByRole("alertdialog", { name: "Confirm enabling pr-mode" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm enable" }));
    expect(apiPatch).toHaveBeenCalledWith(
      "/api/settings",
      expect.objectContaining({ git_settings: expect.objectContaining({ enabled: true }) }),
    );
  });
});
