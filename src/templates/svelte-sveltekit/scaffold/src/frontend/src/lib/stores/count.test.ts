import { get } from "svelte/store";
import { beforeEach, describe, expect, it } from "vitest";

import { count } from "./count";

// Unit test for the {{PROJECT_NAME}} counter store — exercises the EXISTING
// writable exported from ./count.ts. Pure store logic, no SvelteKit runtime.
describe("count store", () => {
  beforeEach(() => {
    count.set(0);
  });

  it("starts at 0", () => {
    expect(get(count)).toBe(0);
  });

  it("increments via update", () => {
    count.update((n) => n + 1);
    expect(get(count)).toBe(1);
  });

  it("sets an explicit value", () => {
    count.set(42);
    expect(get(count)).toBe(42);
  });
});
