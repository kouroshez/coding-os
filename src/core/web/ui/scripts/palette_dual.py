#!/usr/bin/env python3
import itertools

DARK = {
    "folder": "#E8A24A",
    "module": "#B0742C",
    "file": "#B58A6E",
    "import_": "#8A8276",
    "identifier": "#A39A8A",
    "class": "#8B8FF4",
    "interface": "#5B5FE0",
    "variable": "#B9BBF9",
    "function": "#B07CF0",
    "method": "#D0A6FF",
    "route": "#4C9DF0",
    "mcp_tool": "#2DD4D4",
    "tool": "#79E6D8",
    "contract": "#3B82F6",
    "event": "#6FC0FF",
    "doc_file": "#34D399",
    "doc_heading": "#86E05A",
    "doc_frontmatter": "#BCE8A0",
    "doc_external": "#2DD4BF",
    "rule": "#D070D0",
    "skill": "#F25FBE",
    "task": "#FF85C2",
    "hook": "#FF5C7A",
    "community": "#F2913D",
    "unknown": "#9AA0A8",
}
LIGHT = {
    "folder": "#D08A28",
    "module": "#7A4E16",
    "file": "#6E5848",
    "import_": "#8B8270",
    "identifier": "#5F5A50",
    "class": "#4B45C8",
    "interface": "#322C9E",
    "variable": "#6258D8",
    "function": "#6A23BE",
    "method": "#A064E0",
    "route": "#1565C0",
    "mcp_tool": "#0E8A9E",
    "tool": "#1A9DB5",
    "contract": "#0C4F8A",
    "event": "#1F7FD0",
    "doc_file": "#0E8A5E",
    "doc_heading": "#4A8C24",
    "doc_frontmatter": "#6B9E36",
    "doc_external": "#0E7E7E",
    "rule": "#A81C9E",
    "skill": "#C21F72",
    "task": "#C44D9E",
    "hook": "#C71F4E",
    "community": "#C26516",
    "unknown": "#8B8270",
}
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


def _l(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lab(h):
    h = h.lstrip("#")
    r, g, b = (_l(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x / 0.95047), f(y / 1), f(z / 1.08883)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def de(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=False)) ** 0.5


def lum(h):
    h = h.lstrip("#")
    r, g, b = (_l(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cr(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


for name, P, bg in (("DARK", DARK, "#0a0b0e"), ("LIGHT", LIGHT, "#f6f7f9")):
    labs = {k: lab(v) for k, v in P.items()}
    viol = [
        (de(labs[a], labs[b]), a, b)
        for a, b in itertools.combinations(P, 2)
        if a in COMMON and b in COMMON and de(labs[a], labs[b]) < 18
    ]
    lowc = [k for k, v in P.items() if cr(v, bg) < 1.45]  # dot barely separable from bg
    print(f"{name}: common-common <18 dE -> {len(viol)} ; low-bg-contrast(<1.45) -> {lowc}")
    for d, a, b in sorted(viol):
        print(f"   dE={d:.1f} {a} vs {b}")
