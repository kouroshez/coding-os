"""Check or refresh the pinned tool versions inside skill reference docs.

PURPOSE:      Keep every skill's `versions.json` current against the
              authoritative package registry so reference docs never assert a
              stale "latest". One command replaces hand-editing N files.
INPUT:        --root <dir>     repo root to scan (default: cwd).
              --skill <name>   limit to one skill folder.
              --check          report drift, exit 1 if any (CI gate).
              --write          rewrite drifted version+checked in place.
              --offline        validate schema only, no network.
              --json           machine-readable summary on stdout.
              --timeout <s>    per-request timeout (default 8).
OUTPUT:       Human summary on stderr (progress) + table/JSON on stdout.
              Exit 0 = in sync (or written); 1 = drift found (--check) or
              schema error; 2 = usage error.
DEPENDENCIES: stdlib only (urllib, json) — portable across consumer projects.
NOTES:        A skill opts in by shipping `versions.json` next to SKILL.md:
                {"<key>": {"ecosystem": "npm", "package": "next",
                           "version": "16.2.7", "source": "<url>",
                           "checked": "2026-06-04"}}
              Fetch is pluggable per ecosystem; unknown/unreachable entries
              are reported, never silently passed. The diff layer is pure so
              it unit-tests without network. Spec:
              docs/playbooks/skill-authoring.md § Version-pinning mechanism.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

VERSIONS_FILENAME = "versions.json"
REQUIRED_KEYS = ("ecosystem", "package", "version")


# --- ecosystem fetchers ------------------------------------------------------
# Each returns the latest stable version string, or raises on failure. URLs are
# the registry's machine-readable endpoint (see docs/playbooks/skill-authoring.md).

def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "coding-os-skill-refresh"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_text(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "coding-os-skill-refresh"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def _npm(pkg: str, timeout: float) -> str:
    return _get_json(f"https://registry.npmjs.org/{pkg}/latest", timeout)["version"]


def _pypi(pkg: str, timeout: float) -> str:
    return _get_json(f"https://pypi.org/pypi/{pkg}/json", timeout)["info"]["version"]


def _go(module: str, timeout: float) -> str:
    return _get_json(f"https://proxy.golang.org/{module}/@latest", timeout)["Version"].lstrip("v")


def _go_toolchain(_pkg: str, timeout: float) -> str:
    data = _get_json("https://go.dev/dl/?mode=json", timeout)
    return data[0]["version"].removeprefix("go")


def _github(repo: str, timeout: float) -> str:
    # repo == "owner/name"; /releases/latest skips pre-releases (= stable).
    return _get_json(f"https://api.github.com/repos/{repo}/releases/latest", timeout)["tag_name"].lstrip("v")


def _endoflife(product: str, timeout: float) -> str:
    # Best machine-readable source for LTS/current split; [0] = newest cycle.
    return str(_get_json(f"https://endoflife.date/api/{product}.json", timeout)[0]["latest"])


def _k8s(_pkg: str, timeout: float) -> str:
    return _get_text("https://dl.k8s.io/release/stable.txt", timeout).lstrip("v")


def _wordpress(_pkg: str, timeout: float) -> str:
    return _get_json("https://api.wordpress.org/core/version-check/1.7/", timeout)["offers"][0]["version"]


FETCHERS: dict[str, Callable[[str, float], str]] = {
    "npm": _npm,
    "pypi": _pypi,
    "go": _go,
    "gotoolchain": _go_toolchain,
    "github": _github,
    "endoflife": _endoflife,
    "k8s": _k8s,
    "wordpress": _wordpress,
}


# --- pure layer (unit-testable, no IO) ---------------------------------------

class SchemaError(ValueError):
    pass


def validate_entry(key: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise SchemaError(f"{key}: entry must be an object")
    missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
    if missing:
        raise SchemaError(f"{key}: missing required field(s): {', '.join(missing)}")
    eco = entry["ecosystem"]
    if eco not in FETCHERS:
        raise SchemaError(f"{key}: unknown ecosystem '{eco}' (known: {', '.join(sorted(FETCHERS))})")


def is_drift(pinned: str, latest: str) -> bool:
    return pinned.strip().lstrip("v") != latest.strip().lstrip("v")


def load_manifest(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SchemaError(f"{path}: top level must be an object of {{key: entry}}")
    for key, entry in raw.items():
        validate_entry(key, entry)
    return raw


# --- IO layer ----------------------------------------------------------------

def find_manifests(root: Path, skill: str | None) -> list[Path]:
    found = sorted(
        p for p in root.rglob(VERSIONS_FILENAME)
        if "node_modules" not in p.parts and ".venv" not in p.parts
    )
    if skill:
        found = [p for p in found if skill in p.parts]
    return found


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def refresh_manifest(
    path: Path,
    *,
    offline: bool,
    write: bool,
    timeout: float,
    log: Callable[[str], None],
) -> list[dict]:
    """Return one result row per entry; writes the file only when write=True."""
    manifest = load_manifest(path)
    rows: list[dict] = []
    changed = False
    for key, entry in manifest.items():
        row = {"manifest": str(path), "key": key, "package": entry["package"],
               "ecosystem": entry["ecosystem"], "pinned": entry["version"]}
        if offline:
            row["status"] = "schema-ok"
            rows.append(row)
            continue
        try:
            latest = FETCHERS[entry["ecosystem"]](entry["package"], timeout)
        except (urllib.error.URLError, KeyError, IndexError, TimeoutError, ValueError) as exc:
            row["status"] = "unreachable"
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            log(f"  ! {key}: unreachable ({type(exc).__name__})")
            continue
        row["latest"] = latest
        if is_drift(entry["version"], latest):
            row["status"] = "drift"
            log(f"  ~ {key}: {entry['version']} -> {latest}")
            if write:
                entry["version"] = latest
                entry["checked"] = _today()
                changed = True
        else:
            row["status"] = "current"
            if write:
                entry["checked"] = _today()
                changed = True
        rows.append(row)
    if write and changed:
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"  + wrote {path}")
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--check", action="store_true", help="exit 1 on drift")
    parser.add_argument("--write", action="store_true", help="rewrite drifted versions")
    parser.add_argument("--offline", action="store_true", help="schema check only")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timeout", default=8.0, type=float)
    args = parser.parse_args(argv)

    if args.check and args.write:
        print("error: --check and --write are mutually exclusive", file=sys.stderr)
        return 2

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    manifests = find_manifests(args.root.resolve(), args.skill)
    if not manifests:
        log("no versions.json manifests found")
        if args.as_json:
            print(json.dumps({"manifests": 0, "rows": []}))
        return 0

    log(f"scanning {len(manifests)} manifest(s){' (offline)' if args.offline else ''}...")
    all_rows: list[dict] = []
    schema_failed = False
    for i, path in enumerate(manifests, 1):
        log(f"[{i}/{len(manifests)}] {path}")
        try:
            all_rows.extend(refresh_manifest(
                path, offline=args.offline, write=args.write, timeout=args.timeout, log=log))
        except SchemaError as exc:
            schema_failed = True
            log(f"  SCHEMA ERROR: {exc}")

    drift = [r for r in all_rows if r.get("status") == "drift"]
    unreachable = [r for r in all_rows if r.get("status") == "unreachable"]
    if args.as_json:
        print(json.dumps({"manifests": len(manifests), "drift": len(drift),
                          "unreachable": len(unreachable), "rows": all_rows}, indent=2))
    else:
        log(f"\nsummary: {len(all_rows)} entries · {len(drift)} drift · {len(unreachable)} unreachable")

    if schema_failed:
        return 1
    if args.check and drift:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
