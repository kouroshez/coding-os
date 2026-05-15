Run the matrix-targeted verification commands for files that have changed in the current task.

Per [core/rules/test-discipline.md](core/rules/test-discipline.md): never `pytest tests/ -q` mid-task (6 min full sweep). Only run the matrix command(s) tied to changed files.

Steps:
1. Determine the change scope:
   - If `$ARGUMENTS` is provided (file paths), use them.
   - Otherwise run `git diff --name-only` + `git status --porcelain` to gather changed files.
2. Map each changed path to its matrix row (from [AGENTS.md](AGENTS.md) §Verification Matrix). Surface conflicts: if a file matches no row, ask the user before guessing.
3. Build the deduped list of commands to run.
4. State the plan: "I will run: <commands>". Show it before executing — gives the user a chance to redirect.
5. Run each command. Stream output. Stop at first FAIL with the failing line surfaced.
6. On success: append a short work-log note via `cos_work_log_append(task_id=<current>, summary=<one line>)`.
7. On failure: do NOT mark the task `complete`. Suggest: keep in `testing`, fix the failure, re-run.

When a full sweep IS allowed (state it out loud first — per [test-discipline.md](core/rules/test-discipline.md)):
- Pre-merge final gate.
- Cross-cutting refactor touching ≥3 matrix rows.
- User explicitly asked "run all tests".

Output format:
```markdown
## Verification — {N} command(s)

### Plan
- {file pattern} → `{command}`

### Results
- ✅ `{command}` — {duration}
- ❌ `{command}` — {failure summary}, see {line}

### Next step
{recommendation}
```
