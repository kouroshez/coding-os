<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-04-15 -->

# ADR-0001: Adopt Python src-layout

- **Status:** Accepted (2026-04-15)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** packaging, imports, repo-structure

## Context

The repository started flat — `cli/`, `core/`, `adapters/`,
`scripts/` all lived at the root. This worked for early iteration
but ran into three concrete problems as the codebase grew:

1. **Implicit imports.** With code at the root, `from core.X import Y`
   could resolve from CWD even when the package wasn't installed.
   Tests passed locally but broke under `uv tool install` because
   the consumer environment didn't have the implicit path.
2. **Top-level pollution.** Every new directory at the root competed
   with non-code dirs (`docs/`, `tests/`, `archive/`, `.github/`),
   making the top-level `ls` increasingly noisy.
3. **Editable installs vs production drift.** `pip install -e .`
   from the root made `cli`, `core`, `adapters` importable, but
   the production wheel layout was harder to test in isolation.

The Python community standard is **src-layout**: all importable
code lives under `src/`, and `pyproject.toml` lists the packages
explicitly. This forces the imports to go through the installed
package, eliminating CWD-based shortcuts.

## Decision

Adopt src-layout. Move every importable directory under `src/`:

```
src/
├── cli/              # Factory entrypoint (cos command)
├── core/             # Agent-agnostic kernel
│   ├── thinking_os/
│   ├── graph_os/
│   ├── board_os/
│   ├── web/
│   ├── hooks/
│   ├── rules/
│   ├── skills/
│   └── scripts/
├── adapters/         # Per-agent translation
└── templates/        # Per-stack scaffolds
```

Map the import names to file paths in
`[tool.setuptools.package-dir]` so callers continue to write
`from thinking_os.X import Y` (not `from src.core.thinking_os.X`).

The `tests/` directory stays at the root (Python convention — tests
ship with the source, not the wheel).

## Consequences

**Positive:**

- Editable installs and wheel installs behave identically.
- Top-level `ls` is uncluttered.
- The kernel layer (`src/core/`) is visibly distinct from
  per-stack and per-adapter overlays.
- The `core.X` ↔ `X` dual import names smooth the migration
  (legacy `from core.X import Y` still works alongside the new
  `from X import Y`).

**Negative:**

- Every existing path reference in scripts, docs, and tests had
  to be updated (and several broke during the migration — see
  the post-migration sweep commits, especially the `fix(src-layout)`
  series).
- Tooling that hardcoded `core/` instead of `src/core/` needed
  patches (the install-git-hooks script was one casualty —
  see commit fix(scripts): install-git-hooks path resolution post
  src-layout).
- `manifest.json` and golden fixtures had to be regenerated.

**Mitigations:**

- A repeated `make manifest-regen` + `make regen-rules` step is now
  part of the post-edit workflow for any change that touches
  scaffold templates.
- CI runs an editable/source install (`uv sync --extra rag`) only — there is
  no wheel build-and-install step, so package-data omissions do not surface in
  CI by themselves (this is how the H1 wheel-data gap shipped). The regression
  guard is `tests/test_wheel_packaging.py`: it asserts every runtime data tree
  the installed `cos` reads is declared in `[tool.setuptools.package-data]`.

## Alternatives considered

- **Keep flat layout** — rejected; the implicit-import problem was
  the trigger and would have regressed continuously.
- **Adopt `pyproject.toml` namespace packages without src-layout**
  — would have fixed half the problem but kept the top-level
  pollution.
