import { describe, expect, it } from "vitest";

import { normalizeModelRouting } from "./SettingsPage";

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
