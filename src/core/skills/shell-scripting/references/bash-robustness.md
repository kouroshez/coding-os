<!-- domain:UNIVERSAL | layer:reference | ssot:true | updated:2026-06-04 -->
# Bash Robustness — Strict Mode, Traps, Quoting

> P: The exact failure modes strict mode prevents and the idioms that survive spaces, empty matches, and signals.
> R: Writing or reviewing any Bash longer than a one-liner.
> S: Pure Python scripts — see [argument-parsing.md](argument-parsing.md) for the Bash→Python line.
> N: [SKILL.md](../SKILL.md), [script-checklist.md](../assets/script-checklist.md)

> Nav: [Skill](../SKILL.md)

## Strict mode — what each flag actually prevents

| Flag | Without it | With it |
|---|---|---|
| `set -e` | a failed command is ignored; the script ploughs on with bad state | first non-zero exit aborts (except in conditionals) |
| `set -u` | a typo'd `$VARNAME` expands to empty → `rm -rf $DIR/` becomes `rm -rf /` | unset variable is a hard error |
| `set -o pipefail` | `false | true` exits 0 — a failed `curl` in a pipe looks successful | the pipeline's exit is the last non-zero |
| `IFS=$'\n\t'` | word-splitting on spaces mangles filenames with spaces | splits only on newline/tab |

`set -euo pipefail` is the floor. It is not magic — know its three escape hatches:

1. **Conditionals are exempt.** `if grep -q x f; then` does not abort on no-match — that is correct. But a *bare* `grep -q x f` on its own line WILL abort under `-e` when there is no match.
2. **`local x=$(cmd)` hides the exit code** — `local` returns 0, masking `cmd`'s failure. Split: `local x; x=$(cmd)`.
3. **`cmd || true`** deliberately swallows failure — use ONLY when the failure is genuinely fine (e.g. a `grep -c` that legitimately matches nothing). Never use it to silence a failure that matters.

## The `grep` / `find` exit-code trap

`grep` returns exit 1 when it matches nothing; `grep -c` likewise. Under `set -e` that aborts the script even though "zero matches" is a valid answer.

```bash
# Wrong — aborts the whole script when the pattern is simply absent
count=$(grep -c ERROR app.log)

# Correct — capture the count, tolerate zero matches
count=$(grep -c ERROR app.log || true)
[[ -z "$count" ]] && count=0
```

## Traps — cleanup on every exit path

```bash
_tmp="$(mktemp)"
cleanup() { rm -f "$_tmp"; }
trap cleanup EXIT          # runs on success, error (-e), AND Ctrl-C / SIGTERM
```

`EXIT` covers normal return + error abort + most signals. Add `trap 'cleanup; exit 130' INT` only when you need a distinct exit code per signal. Never leave temp files behind for the next run to trip over.

## Quoting — the rule with no exceptions

Always `"$var"`, always `"${array[@]}"`, always `"$@"` (not `$*`). Unquoted expansion re-splits on `IFS` and glob-expands — the source of "works on my machine, deletes your repo on theirs".

```bash
# Wrong — a path with a space becomes two arguments
cp $src $dst

# Correct
cp -- "$src" "$dst"          # -- stops option parsing if $src starts with '-'
```

## Iterating files — never parse `ls`

```bash
# Wrong — breaks on spaces, newlines, globs in names
for f in $(ls *.log); do ... done

# Correct — NUL-delimited, survives any filename
while IFS= read -r -d '' f; do
  process "$f"
done < <(find . -name '*.log' -print0)
```

## Tooling

- **shellcheck** (`koalaman/shellcheck`, pinned in [versions.json](../versions.json)) — static analysis; treat warnings as errors in CI. `make verify-hooks` runs it across the repo's hooks.
- **shfmt** (`mvdan/sh`) — deterministic formatter; `shfmt -i 2 -w script.sh`.

Run both in the script's CI step; a script that shellcheck flags is not shippable.
