#!/usr/bin/env python3
# WCAG contrast for every hook ActionBadge fg/bg pair, both themes.
def _l(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(h):
    h = h.lstrip("#")
    r, g, b = (_l(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cr(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blend(base, alpha, panel):
    bh, ph = base.lstrip("#"), panel.lstrip("#")
    return "#%02x%02x%02x" % tuple(
        round(int(bh[i : i + 2], 16) * alpha + int(ph[i : i + 2], 16) * (1 - alpha))
        for i in (0, 2, 4)
    )


THEMES = {
    "DARK": {
        "panel": "#111317",
        "badges": [
            ("info", "#4c8dff", ("a", "#4c8dff", 0.14)),
            ("err", "#f2576b", ("a", "#f2576b", 0.14)),
            ("warn", "#e0a227", ("a", "#e0a227", 0.14)),
            ("ok", "#3fb950", ("a", "#3fb950", 0.14)),
            ("brand", "#a7abf8", ("a", "#7c82f2", 0.14)),
            ("live", "#45d6e8", ("a", "#45d6e8", 0.16)),
            ("neutral", "#a4abb8", ("a", "#2c313a", 0.40)),
        ],
    },
    "LIGHT": {
        "panel": "#ffffff",
        "badges": [
            ("info", "#0969da", ("hex", "#e7f0fe")),
            ("err", "#cf222e", ("hex", "#fce9ea")),
            ("warn", "#9a6700", ("hex", "#fbf3e0")),
            ("ok", "#1a7f37", ("hex", "#e6f4ea")),
            ("brand", "#4338ca", ("hex", "#eeeffe")),
            ("live", "#0e7490", ("a", "#0e7490", 0.14)),
            ("neutral", "#4a5260", ("a", "#d8dce3", 0.40)),
        ],
    },
}
fails = 0
for tname, t in THEMES.items():
    print(f"=== {tname} (panel {t['panel']}) ===")
    for name, fg, spec in t["badges"]:
        bg = spec[1] if spec[0] == "hex" else blend(spec[1], spec[2], t["panel"])
        r = cr(fg, bg)
        mn = 3.0
        ok = "ok " if r >= mn else "FAIL"
        if r < mn:
            fails += 1
        print(f"  [{ok}] {name:8s} {r:4.1f}:1  fg {fg} on bg {bg}")
print(f"\nTOTAL FAILURES (<3.0): {fails}")
