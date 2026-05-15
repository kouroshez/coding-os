---
name: deployment-cicd
description: Production-ready CI/CD pipelines, container images, and release patterns. Use when designing a CI pipeline, writing Dockerfiles, choosing between blue-green / canary / rolling, setting up semantic versioning, defining a rollback playbook, or migrating from manual deploys to GitOps. Stack-agnostic; recipes target GitHub Actions, Docker, Kubernetes, and the major cloud providers. Pairs with observability (deploy markers in metrics) and incident-response (rollback playbook).
last_reviewed: "2026-05-11"
---

# Deployment + CI/CD — Ship Safely, Roll Back Fast

A practical playbook for the deploy pipeline that gets a feature from "merged" to "in production" reliably. Stack-agnostic core; recipes assume Docker + GitHub Actions + Kubernetes (the 2026 industry default) with callouts for AWS / GCP / Fly.io specifics.

## When to Use This Skill

- Designing CI for a new service — the shape now sets the team's culture.
- Writing or auditing a Dockerfile — bad layers cost minutes per build.
- Choosing between rolling, blue-green, canary, or feature-flag deploys.
- Defining the release process — who clicks deploy, when, and what's reversible.
- Adding semantic versioning + automated changelogs.
- Setting up secrets in CI without leaking them.
- Writing a rollback playbook (preferably *before* you need it).
- Migrating manual deploys → GitOps (Argo CD / Flux).

Skip when: prototyping a script. Real services, real pipelines.

## The Deployment Pipeline — Six Stages

```
commit → build → test → image → deploy(staging) → deploy(prod)
   │       │      │       │           │                │
   <1s    1-3m   1-5m    1-2m        1-5m         1-5m + verify
```

Every stage must be:

- **Idempotent** — re-running produces the same result.
- **Fast-failing** — break early, don't ship to staging if unit tests failed.
- **Observable** — emit deploy markers to metrics so dashboards correlate "the spike" with "the deploy".
- **Reversible** — every forward step has a documented backward step.

**Hard target:** commit → prod within 30 minutes for non-DB-migration changes. Slower than that, the team batches and the per-batch risk skyrockets.

## Dockerfile — the Five-Layer Rule

A good Dockerfile produces a small, secure, cache-friendly image. Five layers, in this order:

```dockerfile
# 1. Base image — minimal, pinned, scanned
FROM python:3.12-slim AS base

# 2. System dependencies — change rarely
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Language dependencies — change with lock file only
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

# 4. Application code — change every commit
COPY src/ src/

# 5. Runtime configuration — labels, user, entrypoint
LABEL org.opencontainers.image.source="https://github.com/org/repo"
RUN useradd --uid 1000 --no-create-home app
USER 1000
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Hard rules:**

- **Pin the base image by digest**, not tag (`python:3.12-slim@sha256:...`). Tags float; digests don't.
- **Multi-stage builds** when you compile assets / TypeScript / Go binaries. Build stage has compilers; runtime stage doesn't.
- **Non-root user** — `USER 1000`. Containers running as root in K8s are a security finding.
- **No secrets in image layers.** `RUN curl -H "Bearer $TOKEN"` leaks the token in image history. Use BuildKit secrets or runtime env vars.
- **Smallest viable base.** `alpine` < `slim` < `bullseye`. Trade-off: alpine has musl libc (occasional compat issues). For Python, `slim` is usually the sweet spot. For Go, `scratch` or `distroless`.
- **HEALTHCHECK** — actively probe the app, not just process liveness.

### Image hygiene checklist

- [ ] Base image pinned by digest
- [ ] Non-root `USER` set
- [ ] Multi-stage build (if any compile step)
- [ ] No secrets baked in (`docker history --no-trunc` reveals nothing sensitive)
- [ ] OCI labels set (`org.opencontainers.image.*`)
- [ ] HEALTHCHECK or K8s readiness/liveness probe defined
- [ ] CVE-scanned by `trivy` / `grype` in CI

## CI Pipeline — GitHub Actions Template

```yaml
# .github/workflows/ci.yml
name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write  # for ghcr.io
  id-token: write  # for OIDC to cloud

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install uv
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run pytest -q --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}

  build-image:
    needs: lint-and-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true
          sbom: true
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository }}:${{ github.sha }}
          severity: CRITICAL,HIGH
          exit-code: "1"
```

**Hard rules:**

- **`concurrency` block** to cancel in-progress runs on the same branch — saves cost and time.
- **OIDC to cloud**, not long-lived access keys. `id-token: write` plus a cloud-side trust policy.
- **Pin actions by SHA** for security-critical workflows, not version tags (`uses: actions/checkout@8e5e7e5...`). Dependabot updates these.
- **SBOM + provenance** on every image (`provenance: true`, `sbom: true`). Required for SLSA L2.
- **CVE scan** as a gate — block merge if HIGH/CRITICAL CVEs present.
- **Lint + test → build → push** stage order. Building a broken image wastes minutes.

## Versioning — Semantic + Auto-Tag

Use **semver** (MAJOR.MINOR.PATCH):

- MAJOR — breaking change to the public API / contract.
- MINOR — backwards-compatible feature add.
- PATCH — backwards-compatible bug fix.

Automate via [Conventional Commits](https://www.conventionalcommits.org) + `semantic-release` (Node), `python-semantic-release`, or `goreleaser`. The commit prefix (`feat:`, `fix:`, `chore:`, `feat!:`) drives the version bump.

Tag the Docker image with all three: `:1.4.2`, `:1.4`, `:1`. Latest goes to mutable `latest`, but production never deploys `latest` — pin a specific digest.

## Deploy Strategies — When to Pick Which

| Strategy | How | Risk | Use For |
|---|---|---|---|
| **Rolling** | Replace pods N at a time | Mixed versions during rollout | Default for stateless services |
| **Blue-green** | Spin up green, switch traffic instantly | Cutover bug = full outage | DB cutovers, critical migrations |
| **Canary** | Send 1% → 5% → 25% → 100% | Need traffic-split + auto-rollback | High-traffic user-facing changes |
| **Feature flag** | Deploy disabled, flip flag per cohort | Flag debt; testing combinatorial states | New features, A/B tests, kill-switches |
| **Shadow** | Send mirror traffic, don't show result | Read-side only, no side effects | Validating perf of a rewrite |

**Default for new services: rolling.** Move to canary when the service has paying users and an incident would matter.

## Rollback — the most important playbook

A deployment system without a rollback button is a system that goes down. Three rules:

1. **One command to roll back.** `argocd app rollback <app> <revision>` or `helm rollback <release> <revision>` or `kubectl rollout undo deploy/<name>`. Practiced quarterly.
2. **Old version warm** for at least 15 minutes after rollout. Don't terminate the old replicas immediately — keep them warm so rollback is instant.
3. **Migrations are forward-compatible.** A rollback shouldn't break because the new code wrote a column the old code doesn't understand. Patterns: expand-contract (add column nullable → backfill → make non-null in next release → remove old column in release after that).

### Forward-only migrations (the pattern)

```
Release 1: add new column `email_verified_at` (nullable)
Release 2: backfill existing rows
Release 3: switch reads to new column; writes still go to both
Release 4: writes only to new column; remove old column reads
Release 5: drop old column
```

Each release is independently rollback-safe.

## Secrets — never in git, never in image

- **Source of truth:** AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault / Sealed Secrets / SOPS.
- **Injection at runtime** via env var or mounted file — never baked into image.
- **CI secrets:** GitHub Actions secrets / OIDC short-lived tokens. Never echo.
- **Rotation:** all production secrets rotated quarterly. Auto-rotation if the system supports it.
- **Pre-commit scan:** `gitleaks`, `trufflehog` run on every PR. Block merge if a secret pattern is found.

## GitOps — the 2026 default

For production K8s: don't `kubectl apply` from a laptop. Use **Argo CD** or **Flux** — the desired state is git, the operator reconciles. Benefits:

- Audit trail (every change is a commit).
- Drift detection (operator notices if someone hand-edited the cluster).
- One-command rollback (`git revert HEAD`).
- PR-based reviews of infra changes.

## Anti-patterns (reject in review)

- **`latest` tag in production manifests** — non-deterministic deploys. Pin digest.
- **Building image inside the cluster** — slow, insecure. Build in CI, ship the image.
- **`kubectl apply -f` from a laptop** — no audit, drifts from git. Use GitOps.
- **Long-lived AWS access keys in GH secrets** — use OIDC.
- **Manual database migrations during deploy** — auto via migration job + forward-compatible pattern.
- **No rollback button** — system that can't be rolled back will go down.
- **Skipping CVE scans because they're noisy** — fix the noise (allowlist with expiry), don't disable the scan.
- **Branch deploys to prod** — only main → prod. Branches go to ephemeral environments.

## Verification (project-specific for coding-os meta-repo)

This skill applies to:
- Container build pipelines that ship coding-os to PyPI / GHCR.
- The `src/templates/<stack>/scaffold/.github/workflows/` files that propagate to consumer projects.
- The release tooling around `uv tool install --editable .` → published wheel.

Pre-merge checks:
- `gh workflow list` shows expected workflows enabled.
- `make verify` green.
- No secret regex matches in the diff (`gitleaks detect --staged`).

## See also

- [observability](../observability/SKILL.md) — deploy markers in dashboards.
- [incident-response](../incident-response/SKILL.md) — rollback as runbook step.
- [security-web](../security-web/SKILL.md) §A05 (Security Misconfig), §A06 (Vulnerable & Outdated Components), §A08 (Software & Data Integrity Failures).
- [db-design](../db-design/SKILL.md) — expand/contract migration discipline.
