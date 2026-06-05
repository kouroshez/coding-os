<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Hub UI Checklist

Run when editing the meta-repo Hub UI (src/core/web/ui/).

## Env + build
- [ ] Client env via `import.meta.env.VITE_*` — never `process.env` (undefined in build).
- [ ] `python3 scripts/check_vite_env.py src/core/web/ui/src/**/*.{ts,tsx}` → `clean`.
- [ ] `make ui-dev` (HMR :5173) for iteration; `make ui-build` to refresh `dist/`.

## API contract (api-contract-discipline)
- [ ] Every field read from a `/api/*` response verified against the producing route / `cos_*` tool — not guessed.
- [ ] Field-name drift checked (e.g. `source_uid`/`target_uid`, not `source`/`target`).
- [ ] Per-project calls go through `/api/p/<slug>/*`.

## React/TS quality
- [ ] `python3 ../../../../core/skills/frontend-fundamentals/scripts/check_frontend.py <files>` clean (re-render/key smells).
- [ ] tsconfig strict (see typescript skill); Sigma.js graph updates batched.
- [ ] zustand state minimal; no derived state duplicated.

## Verify
- [ ] `make ui-build` succeeds; the hub serves the rebuilt `dist/`.
- [ ] `cos hub status` reports healthy symlinks.
