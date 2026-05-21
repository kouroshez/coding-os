import { describe, expect, it } from "vitest";

import { isRTL } from "./text-utils";

describe("isRTL", () => {
  it("returns false for null / undefined / empty", () => {
    expect(isRTL(null)).toBe(false);
    expect(isRTL(undefined)).toBe(false);
    expect(isRTL("")).toBe(false);
  });

  it("returns false for pure-LTR text", () => {
    expect(isRTL("hello world")).toBe(false);
    expect(isRTL("cos hub start")).toBe(false);
    expect(isRTL("123 + 456 = 579")).toBe(false);
  });

  it("detects Persian / Arabic script", () => {
    expect(isRTL("سلام دنیا")).toBe(true);
    expect(isRTL("مرحبا")).toBe(true);
  });

  it("detects Hebrew script", () => {
    expect(isRTL("שלום")).toBe(true);
  });

  it("returns true for mixed text containing any RTL character", () => {
    expect(isRTL("commit message — توضیح فارسی")).toBe(true);
  });
});
