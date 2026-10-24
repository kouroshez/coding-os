<!-- domain:INFRA | layer:asset | ssot:false | updated:2026-06-04 -->
# Dockerfile Ship Checklist

Run before committing a Dockerfile or compose stack.

## Image
- [ ] Base image pinned to an explicit version + `-slim`/`-alpine`/distroless — never `latest`.
- [ ] Multi-stage: build tools/dev-deps in a build stage, runtime copies only the artifact.
- [ ] `USER` set to a non-root user in the runtime stage.
- [ ] `HEALTHCHECK` present for long-running services.
- [ ] `.dockerignore` excludes `.git`, `node_modules`/build outputs, `.env`.

## Cache & size
- [ ] Layers ordered least-volatile → most-volatile (deps before source).
- [ ] `apt/apk` install + cleanup in the same `RUN` (`rm -rf /var/lib/apt/lists/*`).
- [ ] `COPY` (not `ADD`) for local files.
- [ ] `docker history` reviewed — no fat layer leaking the build stage.

## Secrets
- [ ] No secret in `ARG`/`ENV`/layer — BuildKit `--mount=type=secret` for build-time.
- [ ] Runtime secrets injected by the orchestrator, not baked.

## Compose (if present)
- [ ] `depends_on: condition: service_healthy` + real healthchecks (no start-order races).
- [ ] Named volumes for data that must survive `down`.
- [ ] Only necessary `ports:` exposed; services talk by service name.

## Verify
- [ ] `bash scripts/lint_dockerfile.sh <Dockerfile>` → `0 issue(s)`.
- [ ] `docker build` succeeds; final image size sane for the stack.
- [ ] `make skills-check-versions` — engine/compose pins current.
