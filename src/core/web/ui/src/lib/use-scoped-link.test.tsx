import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useScopedLink } from "./use-scoped-link";

function wrapperFor(initialPath: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
  );
}

describe("useScopedLink", () => {
  it("parses the active project slug from a /p/<slug>/* URL", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/p/my-shop/board"),
    });
    expect(result.current.slug).toBe("my-shop");
  });

  it("returns null slug when no project is in scope", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/board"),
    });
    expect(result.current.slug).toBeNull();
  });

  it("scopedLink prepends the slug when a project is active", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/p/my-shop/graph"),
    });
    expect(result.current.scopedLink("board")).toBe("/p/my-shop/board");
    expect(result.current.scopedLink("/graph")).toBe("/p/my-shop/graph");
  });

  it("scopedLink returns the un-scoped path when no project is active", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/graph"),
    });
    expect(result.current.scopedLink("board")).toBe("/board");
  });

  it("scopedLink appends a query-string suffix without inserting a slash", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/p/my-shop/graph"),
    });
    expect(result.current.scopedLink("search", "?q=auth")).toBe("/p/my-shop/search?q=auth");
  });

  it("decodes a percent-encoded slug", () => {
    const { result } = renderHook(() => useScopedLink(), {
      wrapper: wrapperFor("/p/my%20shop/board"),
    });
    expect(result.current.slug).toBe("my shop");
  });
});
