# Grep Reference — Search Skill

## Default excludes (always apply)

```bash
EXCL="--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist \
  --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.next \
  --exclude-dir=vendor --exclude='*.lock' --exclude='*.min.*' --exclude='*.map'"
```

## Core flags

| Need | Flags | Example |
|---|---|---|
| Literal string (no regex) | `-F` | `grep -rnF "foo.bar" . $EXCL` |
| Recursive + follow symlinks | `-R` | use `-R` in this repo (has symlinks) |
| Files only | `-l` | `grep -rlF "x" . $EXCL` |
| Files only, NUL-safe for xargs | `-lZ` | `grep -rlZF "x" . $EXCL \| xargs -0` |
| Multiple patterns | `-e` | `grep -rnF -e "A" -e "B" . $EXCL` |
| Skip binaries | `-I` | `grep -rnFI "x" . $EXCL` |
| Case-insensitive | `-i` | `grep -rnFi "x" . $EXCL` |
| Whole word | `-w` | `grep -rnFw "foo" . $EXCL` |
| Context lines | `-C N` | `grep -rnF -C 2 "x" . $EXCL` |
| Extended regex | `-E` | `grep -rnE "foo[0-9]+" . $EXCL` |
| Count matches | pipe wc | `grep -rnF "x" . $EXCL \| wc -l` |
| Pattern starts with `-` | use `-e` | `grep -rnF -e "-flag" . $EXCL` |

## Variant families (check all before editing)

| Original | Also check |
|---|---|
| `MyClass` | `my_class`, `MY_CLASS`, `"MyClass"`, `'MyClass'`, in imports |
| `myFunction` | `my_function`, `MY_FUNCTION`, `my-function` |
| `FEATURE_FLAG` | `feature_flag`, `feature-flag`, `"FEATURE_FLAG"` |
| `old-route` | `old_route`, `oldRoute`, `/old-route` |

Multi-variant scan:
```bash
grep -rnF -e "MyClass" -e "my_class" -e "MY_CLASS" . $EXCL
```

## Replace options

**Option A — sed** (only when OLD/NEW have no `|`, `&`, `\`, newlines):
```bash
grep -rlZF "OLD" . $EXCL | xargs -0 sed -i.bak 's|OLD|NEW|g'
find . -name '*.bak' -delete
```

**Option B — Python** (any string, always safe):
```bash
export OLD='OLD_STRING' NEW='NEW_STRING'
grep -rlZF "$OLD" . $EXCL | xargs -0 python3 -c '
import os, sys, pathlib
old, new = os.environ["OLD"], os.environ["NEW"]
for f in sys.argv[1:]:
    p = pathlib.Path(f)
    try: t = p.read_text(encoding="utf-8")
    except UnicodeDecodeError: continue
    if old in t: p.write_text(t.replace(old, new), encoding="utf-8")
'
```

Use Option B when OLD/NEW contain `/`, `|`, `&`, `\`, or newlines. Prefer B for complex strings.

## Failure modes

| Symptom | Fix |
|---|---|
| grep finds more after edit | Missed variants — expand scan |
| sed corrupts file | Metachar in string — switch to Python Option B |
| Missing `.md`/`.yaml` files | Add `--include='*.md'` scope |
| Too much noise | Add `--include='*.py'` path prefix |
| No match but symbol exists | Check case, try `-R` not `-r`, check `-I` skip |
| Symlinked file not found | Use `-R` (follows all symlinks) |
