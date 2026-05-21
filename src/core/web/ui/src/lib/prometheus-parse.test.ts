import { describe, expect, it } from "vitest";

import { indexByName, parsePrometheus, sumByName } from "./prometheus-parse";

describe("parsePrometheus", () => {
  it("returns an empty array for empty input", () => {
    expect(parsePrometheus("")).toEqual([]);
  });

  it("skips comment and blank lines", () => {
    const text = ["# HELP cos_web_requests_total total", "# TYPE counter", "", "   "].join("\n");
    expect(parsePrometheus(text)).toEqual([]);
  });

  it("parses a bare metric with no labels", () => {
    const samples = parsePrometheus("cos_web_up 1");
    expect(samples).toHaveLength(1);
    expect(samples[0].name).toBe("cos_web_up");
    expect(samples[0].value).toBe(1);
    expect(samples[0].labels).toEqual({});
  });

  it("parses labels in single or double quotes", () => {
    const samples = parsePrometheus("cos_web_requests_total{route='board.list'} 42.0");
    expect(samples[0].name).toBe("cos_web_requests_total");
    expect(samples[0].value).toBe(42);
    expect(samples[0].labels).toEqual({ route: "board.list" });
  });

  it("skips a line whose value is not finite", () => {
    expect(parsePrometheus("cos_web_bad notanumber")).toEqual([]);
  });

  it("parses multiple samples across lines", () => {
    const text = [
      "cos_web_requests_total{route='a'} 10",
      "cos_web_requests_total{route='b'} 5",
    ].join("\n");
    expect(parsePrometheus(text)).toHaveLength(2);
  });
});

describe("indexByName", () => {
  it("groups samples by metric name", () => {
    const samples = parsePrometheus(
      ["cos_x{l='a'} 1", "cos_x{l='b'} 2", "cos_y 9"].join("\n"),
    );
    const idx = indexByName(samples);
    expect(idx.get("cos_x")).toHaveLength(2);
    expect(idx.get("cos_y")).toHaveLength(1);
    expect(idx.get("missing")).toBeUndefined();
  });
});

describe("sumByName", () => {
  it("sums a counter across all label combinations", () => {
    const samples = parsePrometheus(
      ["cos_hits{r='a'} 10", "cos_hits{r='b'} 5", "cos_other 100"].join("\n"),
    );
    expect(sumByName(samples, "cos_hits")).toBe(15);
  });

  it("returns 0 when the metric is absent", () => {
    expect(sumByName([], "cos_nothing")).toBe(0);
  });
});
