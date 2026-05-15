---
globs: ["src/backend/**/*.py"]
alwaysApply: false
---

# Django Backend Rules (auto-loaded on src/backend/**/*.py)

When editing any Python file under `src/backend/`, follow these standards:

- **Services + selectors pattern** — business logic in `services/`, reads in `selectors/`, views stay thin.
- **Typed exceptions** — raise domain exceptions from `src/core/exceptions.py`, never `Exception`.
- **Error envelope** — every DRF view returns `{"error": {"code", "message", "details"}}` on failure.
- **No N+1** — use `select_related` / `prefetch_related` in selectors.
- **Tests first** — every service method gets a unit test with happy + error paths.

Canonical policy: `docs/engineering/backend-rules.md`
Playbook: `docs/playbooks/backend-api.md`
Primary skill: `python-django`
