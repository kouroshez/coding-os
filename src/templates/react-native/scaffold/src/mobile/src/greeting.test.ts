import { describe, expect, it } from "vitest";

import { greeting } from "./greeting";

describe("greeting", () => {
  it("greets by name", () => {
    expect(greeting("mobile")).toBe("Hello, mobile");
  });
});
