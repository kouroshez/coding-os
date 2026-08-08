#!/usr/bin/env python3
# WCAG 2.x contrast-ratio check for the planned dark+light card/badge tokens.
def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexs):
    h = hexs.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, alpha, bg):
    fh, bh = fg.lstrip("#"), bg.lstrip("#")
    out = []
    for i in (0, 2, 4):
        f = int(fh[i : i + 2], 16)
        b = int(bh[i : i + 2], 16)
        out.append(round(f * alpha + b * (1 - alpha)))
    return "#{:02x}{:02x}{:02x}".format(*tuple(out))


DARK_CANVAS = "#0a0b0e"
LIGHT_CANVAS = "#f6f7f9"

# token values (dark, light)
T = {
    "cos-text": ("#e7eaf0", "#14161b"),
    "cos-muted": ("#a4abb8", "#4a5260"),
    "cos-faint": ("#7d8593", "#646a77"),
    "err": ("#f2576b", "#cf222e"),
    "warn": ("#e0a227", "#9a6700"),
    "ok": ("#3fb950", "#1a7f37"),
    "info": ("#4c8dff", "#0969da"),
}
KIND = {  # (dark chip, light chip)
    "bug": ("#f2576b", "#cf222e"),
    "feature": ("#e0a227", "#9a6700"),
    "chore": ("#3fb950", "#1a7f37"),
    "spike": ("#4c8dff", "#0969da"),
    "docs": ("#c77dff", "#7e22ce"),
    "refactor": ("#2dd4bf", "#0f766e"),
    "test": ("#f0883e", "#c2410c"),
    "security": ("#f2618f", "#a3155f"),
}


def run(theme, canvas, idx):
    print(f"\n=== {theme} (canvas {canvas}) ===")
    fails = 0
    # card text pairs on card body (≈ canvas)
    pairs = [
        ("title", T["cos-text"][idx], canvas, 4.5),
        ("id/meta", T["cos-muted"][idx], canvas, 4.5),
        ("label", T["cos-faint"][idx], canvas, 4.5),
        ("priority P0", T["err"][idx], canvas, 3.0),
        ("priority P1", T["warn"][idx], canvas, 3.0),
    ]
    for name, fg, bg, mn in pairs:
        r = ratio(fg, bg)
        ok = "ok " if r >= mn else "FAIL"
        if r < mn:
            fails += 1
        print(f"  [{ok}] {name:<12} {r:.2f}:1 (min {mn:.1f})")
    # kind badge: chip text on 22%-chip-over-canvas tint
    for k, chips in KIND.items():
        chip = chips[idx]
        bg = blend(chip, 0.22, canvas)
        r = ratio(chip, bg)
        mn = 3.0
        ok = "ok " if r >= mn else "FAIL"
        if r < mn:
            fails += 1
        print(f"  [{ok}] badge {k:<9} {r:.2f}:1 (text {chip} on tint {bg})")
    # status badge: status fg on 14%-status-over-panel
    panel = "#111317" if idx == 0 else "#ffffff"
    for s in ("ok", "warn", "err", "info"):
        fg = T[s][idx]
        bg = blend(fg, 0.14, panel)
        r = ratio(fg, bg)
        mn = 3.0
        ok = "ok " if r >= mn else "FAIL"
        if r < mn:
            fails += 1
        print(f"  [{ok}] status {s:<7} {r:.2f}:1")
    return fails


f1 = run("DARK", DARK_CANVAS, 0)
f2 = run("LIGHT", LIGHT_CANVAS, 1)
print(f"\nTOTAL FAILURES: {f1 + f2}")
