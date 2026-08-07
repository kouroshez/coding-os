import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ModelRoutingSection, normalizeModelRouting } from "./SettingsPage";

vi.mock("@/lib/hooks", () => ({
  useApiGet: (_key: unknown, path: string) => {
    const map: Record<string, unknown> = {
      "/api/config/adapters": {
        adapters: [
          {
            id: "rich",
            label: "Rich",
            runtime: "in_process",
            available: true,
            installed: true,
            dispatch_available: true,
            capabilities: ["dispatch", "model_selection", "effort_selection"],
            efforts: ["low", "high"],
            models: [{ id: "big", label: "Big", default: true }],
          },
          {
            id: "freeform",
            label: "Freeform",
            runtime: "in_process",
            available: true,
            installed: true,
            dispatch_available: true,
            capabilities: ["dispatch", "model_selection"],
            efforts: [],
            models: [],
          },
        ],
        default_model: "big",
        count: 2,
      },
      "/api/cognition/roles": { roles: ["reviewer", "architect"] },
    };
    return { data: map[path] };
  },
}));

describe("normalizeModelRouting", () => {
  it("fills nested defaults from an older partial API payload", () => {
    const routing = normalizeModelRouting({ enabled: false, orchestrator_model: "" });

    expect(routing.cooldown).toEqual({ default_seconds: 300, maximum_seconds: 3600 });
    expect(routing.orchestrator).toEqual({ adapter: "", model: "", effort: "" });
    expect(routing.roles).toEqual({});
  });

  it("preserves supplied nested fields while filling missing siblings", () => {
    const routing = normalizeModelRouting({
      enabled: true,
      cooldown: { default_seconds: 90 },
      roles: { reviewer: { adapter: "codex" } },
    });

    expect(routing.cooldown).toEqual({ default_seconds: 90, maximum_seconds: 3600 });
    expect(routing.roles.reviewer).toEqual({ adapter: "codex", model: "", effort: "" });
  });
});

describe("ModelRoutingSection targets", () => {
  const routing = (roles: Record<string, { adapter?: string; model?: string; effort?: string }>) =>
    normalizeModelRouting({ enabled: true, roles });

  it("keeps a saved target visible when its adapter is no longer available", () => {
    render(
      <ModelRoutingSection
        routing={routing({ reviewer: { adapter: "uninstalled", model: "ghost-model" } })}
        onChange={() => {}}
      />,
    );

    const adapter = screen.getByLabelText("reviewer adapter") as HTMLSelectElement;
    const model = screen.getByLabelText("reviewer model") as HTMLSelectElement;

    expect(adapter.value).toBe("uninstalled");
    expect(model.value).toBe("ghost-model");
    expect(screen.getByText("uninstalled — unavailable")).toBeTruthy();
  });

  it("offers a text field when the adapter selects models but publishes no catalog", () => {
    render(
      <ModelRoutingSection
        routing={routing({ reviewer: { adapter: "freeform", model: "anything-goes" } })}
        onChange={() => {}}
      />,
    );

    const model = screen.getByLabelText("reviewer model");

    expect(model.tagName).toBe("INPUT");
    expect((model as HTMLInputElement).value).toBe("anything-goes");
  });

  it("uses a select bound to the declared catalog when one exists", () => {
    render(
      <ModelRoutingSection
        routing={routing({ reviewer: { adapter: "rich", model: "big", effort: "high" } })}
        onChange={() => {}}
      />,
    );

    const model = screen.getByLabelText("reviewer model");

    expect(model.tagName).toBe("SELECT");
    expect((model as HTMLSelectElement).value).toBe("big");
    expect((screen.getByLabelText("reviewer effort") as HTMLSelectElement).value).toBe("high");
  });
});
