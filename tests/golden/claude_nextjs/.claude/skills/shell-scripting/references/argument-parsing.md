<!-- domain:UNIVERSAL | layer:reference | ssot:true | updated:2026-06-04 -->
# Argument Parsing — `getopts`, manual `case`, and `argparse`

> P: How to take runtime arguments correctly in Bash and Python, and exactly when to abandon Bash for Python.
> R: Any script that takes a flag, a path, or a mode.
> S: A zero-argument one-shot (rare — most "one-shots" grow a flag within a week).
> N: [SKILL.md](../SKILL.md), [bash-robustness.md](bash-robustness.md)

> Nav: [Skill](../SKILL.md)

## Bash — manual `while/case` (preferred for long flags)

`getopts` only handles single-letter flags (`-t`) and no `--long` forms. For readable scripts use a manual loop:

```bash
usage() { echo "usage: $0 --target <env> [--workers N] [--dry-run]" >&2; exit 2; }
target="" ; workers=4 ; dry_run=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)  target="${2:?--target needs a value}"; shift 2 ;;
    --workers) workers="${2:?--workers needs a value}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    --) shift; break ;;                 # explicit end-of-flags
    -*) echo "unknown flag: $1" >&2; usage ;;
    *) break ;;                          # first positional
  esac
done
[[ -n "$target" ]] || { echo "error: --target required" >&2; usage; }
```

Three rules: every flag has a default, a missing required flag prints `usage` and exits non-zero, and `${2:?msg}` guarantees a value-taking flag was actually given one.

### `getopts` — when single-letter is enough

```bash
while getopts ":t:w:nh" opt; do
  case "$opt" in
    t) target="$OPTARG" ;;
    w) workers="$OPTARG" ;;
    n) dry_run=1 ;;
    h) usage ;;
    :) echo "-$OPTARG needs a value" >&2; usage ;;
    \?) echo "unknown -$OPTARG" >&2; usage ;;
  esac
done
```

## Defaults must be consumer-relative, never absolute

```bash
# Wrong — breaks on every machine but the author's
root="/Users/me/project/src/backend"

# Correct — relative default, overridable
root="${1:-src/backend}"
```

Python mirror: `parser.add_argument("--root", default="src/backend", type=Path)`. A script that bakes in `/Users/...` or `/home/...` fails the lint and the review.

## Python — `argparse` (the default past ~50 lines)

```python
parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
parser.add_argument("--root", default="src/backend", type=Path)
parser.add_argument("--workers", default=4, type=int)
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--json", action="store_true", dest="as_json")
args = parser.parse_args(argv)        # pass argv explicitly so it's testable
```

`description=__doc__.split("\n")[0]` reuses the module docstring's first line as `--help` text — one source for both. Take `argv: list[str]` in `main(argv)` rather than reading `sys.argv` inside, so the parser is unit-testable.

## The Bash → Python line

Graduate to Python the moment **any** of these appears:

- structured data in/out (JSON, CSV, an API response you must field-access);
- an array of records / an associative array of structs;
- arithmetic beyond `$(( ))` increments;
- you want unit tests or type hints;
- the script crosses ~50 lines or you reach for `eval`.

A 200-line Bash script with nested `eval` and string-built JSON is a rewrite waiting to happen. Spend the 20 minutes now.
