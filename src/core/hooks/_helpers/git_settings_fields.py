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
            gs = (json.load(fh) or {}).get("git_settings") or {}
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    enabled = "true" if gs.get("enabled") is True else "false"
    integration = gs.get("integration_branch") or "main"
    protected = gs.get("protected_branches")
    if not isinstance(protected, list) or not protected:
        protected = ["production"]
    autonomy = gs.get("autonomy_level") or "draft"
    sys.stdout.write(
        "\t".join([enabled, str(integration), ",".join(str(p) for p in protected), str(autonomy)])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
