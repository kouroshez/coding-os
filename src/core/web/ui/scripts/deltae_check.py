#!/usr/bin/env python3
# Pairwise CIE Lab dE76 check for the proposed graph node palette.
import itertools

PALETTE = {
    "folder": ("#F4B63E", "structure"),
    "module": ("#C0792E", "structure"),
    "file": ("#C2C9D6", "neutral"),
    "import_": ("#4E5666", "neutral"),
    "identifier": ("#7C8696", "neutral"),
    "interface": ("#3B45C8", "code"),
    "class": ("#6D7BF7", "code"),
    "variable": ("#AEB6FF", "code"),
    "function": ("#B15CF5", "code"),
    "method": ("#D9A6FF", "code"),
    "contract": ("#0E6F8C", "api"),
    "route": ("#16A6C0", "api"),
    "event": ("#7AD4FF", "api"),
    "mcp_tool": ("#15CBB4", "api"),
    "tool": ("#79E6D8", "api"),
    "doc_external": ("#2E9E6E", "docs"),
    "doc_file": ("#3FB950", "docs"),
    "doc_heading": ("#86E05A", "docs"),
    "doc_frontmatter": ("#BCE8A0", "docs"),
    "rule": ("#D070D0", "gov"),
    "skill": ("#F25FBE", "gov"),
    "task": ("#FF85C2", "gov"),
    "hook": ("#FF5C7A", "gov"),
    "community": ("#F2761D", "analysis"),
    "unknown": ("#6B7280", "neutral"),
}


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_lab(h):
    h = h.lstrip("#")
    r, g, b = (_lin(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


labs = {k: hex_to_lab(v[0]) for k, v in PALETTE.items()}


def de(a, b):
    return sum((x - y) ** 2 for x, y in zip(labs[a], labs[b], strict=False)) ** 0.5


pairs = sorted((de(a, b), a, b) for a, b in itertools.combinations(PALETTE, 2))
THRESH = 18.0
print(str(len(PALETTE)) + " kinds, " + str(len(pairs)) + " pairs. Threshold dE76 < " + str(THRESH))
print("=== closest 16 pairs ===")
for d, a, b in pairs[:16]:
    cross = "" if PALETTE[a][1] == PALETTE[b][1] else " [cross-family]"
    flag = "  <-- TOO CLOSE" if d < THRESH else ""
    print(f"  dE={d:5.1f}  {a:<16} vs {b:<16}{cross}{flag}")
below = [(d, a, b) for d, a, b in pairs if d < THRESH]
print("\n" + str(len(below)) + " pair(s) below threshold (incl. intentional gray-noise cluster).")

# Real gate: BOTH-common pairs must be >= THRESH. Rare kinds may cluster.
COMMON = {
    "folder",
    "file",
    "module",
    "class",
    "function",
    "method",
    "route",
    "mcp_tool",
    "doc_file",
    "doc_heading",
    "rule",
    "skill",
    "hook",
    "task",
}
violations = [(d, a, b) for d, a, b in pairs if d < THRESH and a in COMMON and b in COMMON]
print("=== GATE: common-vs-common pairs below " + str(THRESH) + " ===")
if violations:
    for d, a, b in violations:
        print(f"  FAIL dE={d:.1f} {a} vs {b}")
else:
    print("  PASS — every common-kind pair is >= " + str(THRESH) + " dE apart.")
