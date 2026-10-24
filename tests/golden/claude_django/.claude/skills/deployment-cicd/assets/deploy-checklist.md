<!-- domain:INFRA | layer:asset | ssot:false | updated:2026-06-04 -->
# Deploy Pipeline Checklist

Run when building or reviewing a CI/CD pipeline or a release.

## Pipeline
- [ ] Stages ordered cheapest-first (lint → typecheck → unit → build → integration → e2e → scan → deploy).
- [ ] Every action pinned to a tag/SHA — no `@main`/`@master`/`@latest`.
- [ ] No secret echoed/printed in a step; secrets from the store, not in YAML.
- [ ] `timeout-minutes` on every job (no hung-job billing).
- [ ] Dependencies cached; independent stages parallel.
- [ ] `python3 scripts/lint_workflow.py <workflow files>` → `clean`.

## Release
- [ ] Semantic version + tag; immutable artifact addressed by tag (never re-deploy `latest`).
- [ ] Changelog generated from Conventional Commits.
- [ ] Deploy strategy chosen (rolling / blue-green / canary) with the trade-off understood.

## Safety
- [ ] Rollback is one documented command, tested.
- [ ] Migrations are backward-compatible with the running version (expand→contract).
- [ ] Deploy marker emitted to metrics (correlate regressions to releases).
- [ ] Health check / smoke test gates the traffic switch.

## Verify
- [ ] `make skills-check-versions` — Docker/k8s/action pins current (where pinned).
