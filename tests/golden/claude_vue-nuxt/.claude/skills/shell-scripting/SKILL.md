---
name: shell-scripting
tier: quality
domain: [universal]
description: Write production-grade shell and CLI scripts — Bash and Python. Use when authoring or reviewing any script, Makefile target, hook, CI step, or automation that takes input, does work, and reports a result. Enforces runtime arguments (not hardcoded paths), fail-closed error handling, progress/observable output, idempotency, algorithmic efficiency, and precise machine-readable results. Triggers — "write a script", "bash script", "make target", "automate", "cron job", "CLI tool", any `*.sh`/`scripts/*.py`. Pairs with clean-code (naming/structure), deployment-cicd (CI steps), observability (log hygiene), hook-authoring (coding-os hooks).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Shell & CLI Scripting

A script is a **contract**: given inputs, do exactly one job, report a precise result, fail loud on anything unexpected. A script that hardcodes a path, swallows errors, or prints a paragraph the caller must parse is a liability — it breaks silently in the next environment and taxes every agent that runs it. This skill makes "robust, data-driven, observable" the default shape.

> Scaffold a compliant script instead of hand-writing the boilerplate:
> `python3 scripts/new_script.py --lang bash --name deploy --root .`
> Lint an existing one against the discipline:
> `bash scripts/lint_script.sh path/to/script.sh`

## The seven non-negotiables

Every script — Bash or Python — satisfies all seven. The checklist in [assets/script-checklist.md](assets/script-checklist.md) is the ship gate.

1. **Runtime arguments, never hardcoded.** Inputs come from flags with sane defaults. No literal machine paths, no baked-in hostnames, no magic constants buried in the body.
2. **Fail-closed.** Any unmet precondition or sub-command failure stops the script with a non-zero exit and a message — never continue on error.
3. **Idempotent.** Re-running is safe: detect already-done state, refuse to clobber (or require `--force`).
4. **Observable.** Progress to stderr for anything slow; a final, parseable result (one line or `--json`) on stdout.
5. **Precise output.** stdout is the *result* a caller consumes; stderr is *narration*. Never mix them.
6. **Algorithmically honest.** No O(n²) where a set/index is O(n). Stream large inputs; bound memory. State complexity when non-obvious.
7. **Documented header.** `PURPOSE / INPUT / OUTPUT / DEPENDENCIES / NOTES` at the top — the contract in five lines.

## Bash — the robust preamble (copy, don't retype)

```bash
#!/usr/bin/env bash
# deploy.sh — PURPOSE: ... / INPUT: ... / OUTPUT: ... / DEPS: ... / NOTES: ...
set -euo pipefail          # -e exit on error · -u unset var is error · -o pipefail catch piped failures
IFS=$'\n\t'                # safe word-splitting (no space-splitting surprises)

cleanup() { rm -f "${_tmp:-}"; }
trap cleanup EXIT          # run on ANY exit path — success, error, or signal
```

Why each flag matters — bad→good:

```bash
# Wrong — silent data loss: cd fails, rm runs in the WRONG directory
cd "$build_dir"
rm -rf ./*

# Correct — set -e aborts before rm if cd fails; quoting survives spaces
set -euo pipefail
cd "$build_dir"            # aborts here if $build_dir is unset (-u) or missing (-e)
rm -rf -- "${build_dir:?build_dir required}"/*
```

```bash
# Wrong — pipefail off: the pipeline "succeeds" even though curl failed
curl -s "$url" | jq .version          # exit 0 even on 404

# Correct
set -o pipefail
curl -fsS "$url" | jq .version        # -f makes curl fail on HTTP error; pipefail propagates it
```

Quoting + `grep` exit-code traps (the two that bite every script): always `"$var"`, and a `grep`/`grep -c` that matches nothing returns exit 1 — under `set -e` that kills the script. Guard it: `count=$(grep -c foo file || true)`. Full rules → [references/bash-robustness.md](references/bash-robustness.md).

## Arguments — `getopts` (Bash) / `argparse` (Python)

```bash
# Bash — flags with defaults, a usage(), and a required-arg check
usage() { echo "usage: $0 --target <env> [--dry-run]" >&2; exit 2; }
target="" ; dry_run=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="${2:?--target needs a value}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[[ -n "$target" ]] || { echo "error: --target is required" >&2; usage; }
```

Python scripts use `argparse` with `--root` defaulting to a consumer-relative path (`src/backend`), never an absolute one. Full comparison + when to graduate from Bash to Python → [references/argument-parsing.md](references/argument-parsing.md).

## Progress + result discipline

```bash
log() { printf '%s\n' "$*" >&2; }        # narration → stderr
log "[1/3] fetching..."                    # progress the caller can ignore
log "[2/3] transforming..."
printf '{"changed":%d,"skipped":%d}\n' "$changed" "$skipped"   # result → stdout, parseable
```

The rule that collapses agent cost: **emit the minimum the caller needs to decide the next step, not a transcript.** A script that prints one JSON line replaces ten tool calls the agent would otherwise spend re-deriving state. Quiet by default; `--verbose` opts into detail.

## When Bash, when Python

| Reach for Bash | Reach for Python |
|---|---|
| ≤ ~50 lines, glue of existing CLIs | parsing/transforming structured data (JSON, CSV) |
| process orchestration, file moves | non-trivial control flow, data structures |
| no arrays-of-structs, no math | needs tests, types, or stdlib beyond coreutils |

Past ~50 lines or the first associative-array-of-records, graduate to Python. A 200-line Bash script with nested `eval` is a maintenance trap — the line where you reach for `eval` is the line you should have been in Python.

## `make` targets

A Makefile target is a script too: `.PHONY` it, one job per target, `@` to quiet the echo, fail-closed (make stops on non-zero by default — don't `|| true` away real failures). Document with `## comment` so `make help` lists it.

## Anti-patterns (reject on sight)

- Hardcoded `/Users/...`, `/home/...`, or a literal hostname → take a flag.
- `set -e` absent, or defeated by a trailing `|| true` on a command whose failure matters.
- `cmd2` running after `cmd1` failed because there is no `&&` and no `set -e`.
- stdout polluted with progress so the caller can't parse the result.
- Re-running the script doubles the effect (not idempotent).
- Parsing `ls` output, or `for f in $(ls)` — use a glob or `find -print0 | while read -d ''`.
- `eval` on interpolated input — almost always a quoting bug or a Python signal.

## See also

- [references/bash-robustness.md](references/bash-robustness.md) — strict mode, traps, quoting, the `grep` exit trap.
- [references/argument-parsing.md](references/argument-parsing.md) — `getopts` vs `argparse`, the Bash→Python line.
- [assets/script-checklist.md](assets/script-checklist.md) — the ship gate.
- [docs/playbooks/skill-authoring.md](../../../docs/playbooks/skill-authoring.md) § scripts contract — why every skill's scripts obey this.
