#!/usr/bin/env python3
"""Codemod: Tailwind named-color utilities -> --cos-* tokens (Cortex).
Usage: color_codemod.py [--apply]   (default = dry run, prints per-file counts)
The mapping IS the enterprise rule (docs/engineering/design-system.md)."""
import re, sys, pathlib

ROOT = pathlib.Path("src/core/web/ui/src")
EXEMPT = {  # canonical canvas / single-source maps (WebGL can't read CSS vars)
    "node-colors.ts", "graph-adapter.ts", "useSigma.ts", "BrainGraph3D.tsx",
    "agentPresenceVisuals.ts", "kindColors.ts", "charts.tsx", "theme-store.ts",
}
FAMILY_ROLE = {
    "rose": "err", "red": "err", "pink": "err",
    "emerald": "ok", "green": "ok", "lime": "ok",
    "amber": "warn", "yellow": "warn", "orange": "warn",
    "sky": "info", "blue": "info",
    "violet": "brand", "fuchsia": "brand", "indigo": "brand", "purple": "brand",
    "cyan": "live", "teal": "live",
}
NEUTRALS = {"zinc", "gray", "slate", "neutral", "stone"}
SOLID = {"err": "--cos-err", "ok": "--cos-ok", "warn": "--cos-warn",
         "info": "--cos-info", "brand": "--cos-brand-text", "live": "--cos-live"}
EDGE = {"err": "--cos-err", "ok": "--cos-ok", "warn": "--cos-warn",
        "info": "--cos-info", "brand": "--cos-accent", "live": "--cos-live"}
TINT = {"err": "--cos-err-tint", "ok": "--cos-ok-tint", "warn": "--cos-warn-tint",
        "info": "--cos-info-tint", "brand": "--cos-brand-tint", "live": "--cos-live"}

UTIL_RE = re.compile(
    r"\b(text|bg|border|ring-offset|ring|from|via|to|fill|stroke|shadow|outline|divide|decoration)"
    r"-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
    r"-(\d{2,3})(/\d+)?")

def repl(m):
    util, fam, shade = m.group(1), m.group(2), int(m.group(3))
    if fam in NEUTRALS:
        if util in ("text", "fill", "stroke", "decoration"):
            tok = "--cos-text" if shade <= 300 else ("--cos-muted" if shade <= 550 else "--cos-faint")
            return f"{util}-[var({tok})]"
        if util in ("border", "ring", "divide", "outline", "ring-offset"):
            return f"{util}-[var(--cos-border)]"
        if util in ("bg", "from", "via", "to"):
            tok = "--cos-inset" if shade >= 800 else "--cos-panel"
            return f"{util}-[var({tok})]"
        if util == "shadow":
            return ""
        return m.group(0)
    role = FAMILY_ROLE[fam]
    if util in ("text", "fill", "stroke", "decoration"):
        return f"{util}-[var({SOLID[role]})]"
    if util in ("border", "ring", "divide", "outline", "ring-offset"):
        return f"{util}-[var({EDGE[role]})]"
    if util in ("bg", "from", "via", "to"):
        return f"{util}-[var({TINT[role]})]"
    if util == "shadow":
        return ""
    return m.group(0)

apply = "--apply" in sys.argv
total = 0
for p in sorted(ROOT.rglob("*.tsx")) + sorted(ROOT.rglob("*.ts")):
    if p.name in EXEMPT or "/test/" in str(p):
        continue
    src = p.read_text()
    new, n = UTIL_RE.subn(repl, src)
    if n:
        total += n
        print(f"{n:3d}  {p.relative_to(ROOT)}")
        if apply:
            p.write_text(new)
print(f"\nTOTAL utilities {'rewritten' if apply else 'to rewrite'}: {total}")
