<!-- domain:UNIVERSAL | layer:asset | ssot:false | updated:2026-06-04 -->
# Script Ship Checklist

Run before committing any script, hook, or `make` target. Every box ticked, or it does not ship.

## The seven non-negotiables
- [ ] **Arguments, not constants** — every input is a flag with a sane default; zero hardcoded machine paths / hosts / magic numbers.
- [ ] **Fail-closed** — Bash: `set -euo pipefail`. Python: explicit non-zero exit on any unmet precondition. No `|| true` on a failure that matters.
- [ ] **Idempotent** — re-running is safe; already-done state is detected; clobbering requires `--force`.
- [ ] **Observable** — progress to stderr for slow work; final parseable result (one line or `--json`) on stdout.
- [ ] **stdout = result, stderr = narration** — never mixed.
- [ ] **Algorithmically honest** — no O(n²) where a set/index works; large inputs streamed; memory bounded.
- [ ] **Header present** — `PURPOSE / INPUT / OUTPUT / DEPENDENCIES / NOTES`.

## Bash-specific
- [ ] Shebang `#!/usr/bin/env bash`.
- [ ] `IFS=$'\n\t'` when word-splitting matters.
- [ ] `trap cleanup EXIT` if any temp file / lock is created.
- [ ] All expansions quoted: `"$var"`, `"${arr[@]}"`, `"$@"`.
- [ ] `grep`/`grep -c` that may match nothing wrapped with `|| true`.
- [ ] No `for f in $(ls ...)` — glob or `find -print0`.
- [ ] `shellcheck -S warning` clean; `shfmt` formatted.

## Python-specific
- [ ] `argparse` with explicit `main(argv)` (testable).
- [ ] `--root` / path defaults are consumer-relative, never absolute.
- [ ] stdlib-only unless a dependency is justified.
- [ ] Pure logic separated from IO so it unit-tests without network/fs.

## Verify
- [ ] `bash scripts/lint_script.sh <file>` → `0 issue(s)`.
- [ ] Ran it twice — second run is a no-op (idempotent).
- [ ] `make verify-hooks` green (for hooks / `src/core/**` scripts).
