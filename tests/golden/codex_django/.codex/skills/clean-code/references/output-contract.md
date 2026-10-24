# Output Contract — Worked Shapes

Companion to [SKILL.md § 4b](../SKILL.md). The normative rule lives there; this
file is the format, the progress shapes, and the exit-code contract.

## The marker set

`[OK]` · `[WARN]` · `[FAIL]` · `[SKIP]` — the vocabulary `cos doctor` already
speaks across its checks (`SEV_PASS` / `SEV_WARN` / `SEV_FAIL` in
[src/cli/_doctor_shared.py](../../../../cli/_doctor_shared.py)). It is the SSOT because it already exists and is
already grep-able; a second vocabulary would be the drift this rule exists to
end.

| Marker | Means | Exit contribution |
|---|---|---|
| `[OK]` | The check ran and passed | 0 |
| `[WARN]` | Ran, passed, but something needs attention later | 0 |
| `[FAIL]` | Ran and failed, or could not run | non-zero |
| `[SKIP]` | Deliberately not run, with the reason on the same line | 0 |

`[SKIP]` always carries its reason. A skip with no reason reads as a pass and is
how a suite quietly stops covering something.

```python
# GOOD
print(f"[OK]   {name}")
print(f"[FAIL] {name}: expected {expected!r}, got {actual!r} — repro: {command}")
print(f"[SKIP] {name}: needs the rag extra (uv sync --extra rag)")

# BAD — four vocabularies, and the failure is not actionable
print(f"✅ {name}")
print(f"ERROR: {name} failed")
print("PASS")
print(f"{len(failures)} checks failed")
```

## Progress — never silent while working

Silence and a hang look identical. Two shapes cover almost everything:

```python
# Per-unit, when the unit count is known
for index, unit in enumerate(units, start=1):
    print(f"[{index}/{len(units)}] {unit.name}", file=sys.stderr)
    ...

# Phase announcement, when one step can outlast a couple of seconds
print("[..] indexing 4,520 files (~30s)", file=sys.stderr)
```

Progress goes to **stderr**, results to **stdout** — so `script > results.txt`
still shows the operator what is happening, and a JSON mode stays parseable.
That is the same split the Hub's job runner already relies on: `cos init`
streams its phase markers to stderr precisely so `--format json` keeps stdout
pure.

A counter is not a decoration. `[2841/4520]` answers "is it stuck, and how long
left?" — the two questions that decide whether someone kills the run.

## Summary line

End every multi-unit run with one line that carries the totals, and make the
totals add up to the units attempted:

```text
[OK] 4518 passed, 2 skipped, 0 failed in 31.4s
[FAIL] 4515 passed, 2 skipped, 3 failed in 31.4s — rerun: make verify-hooks
```

The rerun command on the failure line is the point. A summary the reader has to
translate back into a command has moved the work, not reported it.

## Exit codes

`0` = every unit passed or was deliberately skipped. Non-zero = at least one
`[FAIL]`. Never exit `0` on a failure "because the output says so" — the caller
is usually CI or a hook, and neither reads prose.

Hooks are the one documented exception and have their own contract: `0` =
pass/warn, `2` = block, nothing else ([hook-authoring](../../hook-authoring/SKILL.md)).

## Anti-patterns

- A run that prints nothing until it finishes, then prints everything.
- Progress on stdout, so redirecting results loses the operator's view.
- `[FAIL]` without expected/actual, or without the reproduction command.
- A skip with no reason.
- Colour or emoji as the *only* severity signal — it disappears in a log file,
  in CI, and for anyone using a screen reader.
- A summary whose counts do not sum to the units attempted (the missing ones are
  exactly the units that silently never ran).
