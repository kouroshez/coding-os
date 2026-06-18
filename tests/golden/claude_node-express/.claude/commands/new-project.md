Scaffold a new coding-os project non-interactively — the official agent recipe (TASK-359).

Steps:
1. Discover what's available (read-only):
   - `cos list-stacks --format json` → stacks (grouped by `language`) + `presets`.
   - `cos skills-list --stack <id> --format json` → required/recommended/optional skills for a stack.
2. Preview the composition BEFORE writing anything:
   - `cos init --preset <id> --dry-config` (or `--template a --template b --dry-config`)
   - Read the swimlane union and the reported merge conflicts (later stack wins). Nothing is written.
3. Create in one shot (every Composer option has a flag — full parity, incl. multi-agent + module toggles):

```bash
cos init \
  --agent claude \                   # one+ adapters, comma-separated: --agent claude,codex
  --preset nextjs-fastapi \          # OR: --template go-fiber --template fastapi
  --name my-app -d /path/to/parent \ # omit --name only in interactive shells
  --skills redis,docker \            # extra core skills (validated; see cos skills-list)
  --disable-module memory \          # optional, repeatable: turn a subsystem off at create
  --summary "One to two paragraphs describing the product, its users, and what matters most." \
  --yes --no-index
```

4. Verify: exit code 0; `--format json` emits the summary object. The project self-registers in the hub; `--summary` seeds `docs/_meta/project-description.md` (the description→PRD intake).

Rules:
- Non-TTY without `--yes` fails fast naming the missing flags — never rely on prompts in automation.
- `--preset` and `--template` are mutually exclusive; unknown skills/stacks/presets exit 2 listing what exists.
- `--agent` takes one or more adapters (`claude`, `codex`), comma-separated — a project may host several.
- `--disable-module <id>` (repeatable) turns a subsystem off at create: `docs`, `tasks`, `graph`, `memory`, `design`. `kernel` can't be disabled and `tasks` needs `docs` (unknown/kernel exit 2). Mirrors the Composer module chips; `cos module list` shows the result.
- Don't pass `--name` you can't validate: `^[a-z0-9][a-z0-9._-]{0,63}$`.
