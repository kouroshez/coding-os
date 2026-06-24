"""Emit hub-settings.json git_settings as one tab-separated line.

python3 fallback for cos-env.sh when jq is absent (a missing jq must not
silently downgrade an enabled pr-mode project to trunk). argv[1] = path to
hub-settings.json; prints `enabled\tintegration\tprotected(csv)\tautonomy`,
matching the jq `@tsv` filter. Never raises — any error prints nothing.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
        gs = data.get("git_settings") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    # Non-dict git_settings (missing/null/string/list) → emit nothing = trunk,
    # honoring the "never raises" contract (review finding 5).
    if not isinstance(gs, dict):
        return 0
    enabled = "true" if gs.get("enabled") is True else "false"
    integration = gs.get("integration_branch") or "main"
    # Match jq's `// ["production"]` exactly (review finding 6): default ONLY when
    # the key is absent or null; an explicit list (including [] = the "None" preset)
    # is honored; a non-list (e.g. a bare string) fails closed to trunk like jq does,
    # not silently coerced to a default that would enable pr-mode on a jq-less host.
    protected = gs.get("protected_branches", ["production"])
    if protected is None:
        protected = ["production"]
    if not isinstance(protected, list):
        return 0
    autonomy = gs.get("autonomy_level") or "draft"
    sys.stdout.write(
        "\t".join([enabled, str(integration), ",".join(str(p) for p in protected), str(autonomy)])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
