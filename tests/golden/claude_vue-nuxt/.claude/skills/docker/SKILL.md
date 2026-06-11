---
name: docker
tier: infra
domain: [infra]
description: Build small, secure, reproducible container images and compose stacks. Use when writing or reviewing a Dockerfile, debugging a bloated/slow image build, setting up docker-compose for local dev, adding a healthcheck, handling build secrets, or hardening a container (non-root, minimal base). Triggers — "Dockerfile", "docker build", "docker-compose", "containerize", "image is huge", "layer cache", "multi-stage", any `Dockerfile`/`compose.yaml`. Pairs with deployment-cicd (CI builds + registries + k8s — this skill is the image/compose craft), linux-sysadmin (the host), security-web (runtime hardening).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Docker — Images & Compose

An image is a liability proportional to its size and privilege: every MB ships, every package is attack surface, every root container is a host risk. The craft is small, reproducible, least-privilege images. CI/CD, registries, and orchestration belong to [deployment-cicd](../deployment-cicd/SKILL.md); this skill is the Dockerfile and compose itself.

> Lint a Dockerfile against the rules below:
> `bash scripts/lint_dockerfile.sh path/to/Dockerfile`

## Multi-stage — build fat, ship thin

```dockerfile
# Wrong — toolchain + source + caches all ship; 1.2 GB; runs as root
FROM node:26
COPY . .
RUN npm install && npm run build
CMD ["node", "dist/server.js"]

# Correct — build stage discarded; runtime carries only the artifact; ~180 MB
FROM node:26-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci                      # ci (not install) = reproducible, lockfile-exact
COPY . .
RUN npm run build

FROM node:26-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
USER node                       # never run as root
EXPOSE 8080
HEALTHCHECK CMD node healthcheck.js || exit 1
CMD ["node", "dist/server.js"]
```

The build stage carries compilers and dev deps; the runtime stage copies only the artifact. Result is smaller, faster to pull, and has less attack surface. Full optimization → [references/dockerfile-optimization.md](references/dockerfile-optimization.md).

## Layer cache — order from least to most volatile

```dockerfile
# Wrong — any source change busts the dependency layer; npm ci re-runs every build
COPY . .
RUN npm ci

# Correct — deps cached until package*.json changes; source edits skip the install
COPY package*.json ./
RUN npm ci
COPY . .                        # volatile source last
```

Docker caches per layer; a layer rebuilds when its inputs or any prior layer changes. Put rarely-changing things (dependency manifests, `RUN apt install`) **before** frequently-changing things (source). A `.dockerignore` (excluding `node_modules`, `.git`, `*.log`) keeps the build context — and the cache key — small.

## Never bake secrets

```dockerfile
# Wrong — the secret is in the image history forever, readable by anyone who pulls it
ARG API_KEY
ENV API_KEY=$API_KEY

# Correct — BuildKit secret mount: available during build, never in a layer
RUN --mount=type=secret,id=npmtoken \
    NPM_TOKEN="$(cat /run/secrets/npmtoken)" npm ci
```

`ARG`/`ENV` secrets persist in `docker history` and every pulled copy. Use BuildKit `--mount=type=secret` for build-time, and inject runtime secrets via the orchestrator's secret store (env from a vault, not the image). Runtime hardening (caps, read-only fs) → [security-web](../security-web/SKILL.md).

## Compose for local dev

```yaml
# compose.yaml
services:
  api:
    build: .
    ports: ["8080:8080"]
    environment: { DATABASE_URL: postgres://app:app@db:5432/app }
    depends_on:
      db: { condition: service_healthy }   # wait for db READY, not just started
  db:
    image: postgres:18
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      retries: 5
```

`depends_on: condition: service_healthy` is the fix for "app starts before the DB is ready" — a plain `depends_on` only waits for the container to *start*, not to be *usable*. Patterns → [references/compose-patterns.md](references/compose-patterns.md).

## Anti-patterns (reject on sight)

- `FROM ubuntu` / `FROM node` with no tag → pins to a moving `latest`; pin a version + `-slim`/`-alpine`.
- No `USER` directive → container runs as root.
- `ADD` for a local file → use `COPY` (`ADD` also fetches URLs + auto-extracts tarballs — surprising).
- `RUN apt update` and `apt install` in separate layers → stale package index; combine + `rm -rf /var/lib/apt/lists/*`.
- Secret in `ARG`/`ENV` → leaks in history.
- `COPY . .` before installing deps → busts the cache every source edit.
- No `.dockerignore` → ships `.git`, `node_modules`, secrets into the build context.

## See also

- [references/dockerfile-optimization.md](references/dockerfile-optimization.md) — multi-stage, cache, base images, size.
- [references/compose-patterns.md](references/compose-patterns.md) — healthchecks, depends_on, networks, profiles.
- [assets/dockerfile-checklist.md](assets/dockerfile-checklist.md) — the ship gate.
- [deployment-cicd](../deployment-cicd/SKILL.md) · [linux-sysadmin](../linux-sysadmin/SKILL.md) · [security-web](../security-web/SKILL.md).
