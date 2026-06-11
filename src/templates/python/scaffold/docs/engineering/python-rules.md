# Python Engineering Rules

Project: {{PROJECT_NAME}} · Updated: {{DATE}}

## Layout

- **Package code** in `src/<package>/` (src-layout) — keeps imports honest in tests.
- **Tests** in `tests/`, mirroring the package tree; fixtures in `tests/conftest.py`.
- **Packaging SSOT** is `pyproject.toml` — version, deps, entry points; no `setup.py`.

## Style & safety

- Type hints on every public signature; `from __future__ import annotations` in new modules.
- Fail closed: raise typed, domain-specific exceptions; never return silent fallbacks.
- No bare `except Exception` without a debug log; fire-and-forget helpers log and continue.
- Resolve paths with `pathlib.Path` and `.resolve()` before `relative_to()` (macOS /tmp quirk).
- Magic numbers/strings become named constants at module top.

## Dependencies

- Add runtime deps to `pyproject.toml` with a floor pin (`>=`); dev-only deps to the dev extra.
- Prefer the stdlib; a new dependency needs a reason the stdlib can't cover.

## Testing

- Every except/validation branch gets a test asserting type and message.
- Keep unit tests offline and sub-second; mark anything slower as integration.
