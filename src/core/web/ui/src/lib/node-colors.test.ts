import { describe, expect, it } from "vitest";

import {
  ALL_KINDS,
  NODE_COLORS,
  NODE_COLORS_LIGHT,
  ROOT_COLOR,
  isRootUid,
  kindColor,
  normalizeKind,
} from "./node-colors";

describe("normalizeKind", () => {
  it("maps null / undefined / empty to 'unknown'", () => {
    expect(normalizeKind(null)).toBe("unknown");
    expect(normalizeKind(undefined)).toBe("unknown");
    expect(normalizeKind("")).toBe("unknown");
  });

  it("maps an unrecognized kind to 'unknown'", () => {
    expect(normalizeKind("definitely-not-a-kind")).toBe("unknown");
  });

  it("is case-insensitive", () => {
    // Every canonical kind round-trips through its own upper-cased form.
    for (const kind of ALL_KINDS) {
      expect(normalizeKind(kind.toUpperCase())).toBe(kind);
    }
  });

  it("round-trips every canonical kind to itself", () => {
    for (const kind of ALL_KINDS) {
      expect(normalizeKind(kind)).toBe(kind);
    }
  });
});

describe("kindColor", () => {
  it("returns a hex/rgb color string for every canonical kind", () => {
    for (const kind of ALL_KINDS) {
      const color = kindColor(kind);
      expect(typeof color).toBe("string");
      expect(color.length).toBeGreaterThan(0);
    }
  });

  it("falls back to the 'unknown' color for a bad kind", () => {
    expect(kindColor("garbage")).toBe(NODE_COLORS.unknown);
  });
});

describe("NODE_COLORS", () => {
  it("has a color entry for every kind in ALL_KINDS", () => {
    for (const kind of ALL_KINDS) {
      expect(NODE_COLORS[kind]).toBeDefined();
    }
  });
});

describe("root focal anchor (TASK-408)", () => {
  it("recognizes both repo-root uid forms and nothing else", () => {
    expect(isRootUid("folder:.")).toBe(true);
    expect(isRootUid("folder:")).toBe(true);
    expect(isRootUid("folder:src")).toBe(false);
    expect(isRootUid("code:file:src/main.py")).toBe(false);
  });

  it("reserves the root color outside the categorical kind palette (both themes)", () => {
    // The anchor must never collide with a data-driven kind hue, in
    // either palette — that is the whole point of a reserved focal color.
    const dark = Object.values(NODE_COLORS).map((c) => c.toLowerCase());
    const light = Object.values(NODE_COLORS_LIGHT).map((c) => c.toLowerCase());
    expect(dark).not.toContain(ROOT_COLOR.toLowerCase());
    expect(light).not.toContain(ROOT_COLOR.toLowerCase());
  });
});
