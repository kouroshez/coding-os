<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-06-04 -->
# Dockerfile Optimization — Size, Cache, Base Images

> P: Make images small, builds fast, and layers cacheable.
> R: Writing or shrinking a Dockerfile; a build is slow or the image is huge.
> S: Orchestration / registry / CI — that's [deployment-cicd](../../deployment-cicd/SKILL.md).
> N: [SKILL.md](../SKILL.md), [compose-patterns.md](compose-patterns.md)

> Nav: [Skill](../SKILL.md)

## Base image — smaller is safer

| Base | Size | Use when |
|---|---|---|
| `*-alpine` | ~5–50 MB | static binaries, Go; musl libc (watch glibc-only deps) |
| `*-slim` (Debian) | ~50–120 MB | most apps; glibc, no build tools |
| `distroless` | ~20–50 MB | runtime only, no shell — hardest to exploit |
| full (`ubuntu`, `node`) | 300 MB–1 GB | build stage only, never runtime |

Pin a digest or exact version (`node:26.0.0-slim`), never `latest` — a moving
base breaks reproducibility and silently changes your runtime.

## Multi-stage — the size lever

The runtime stage `COPY --from=build` only the artifact (binary, `dist/`,
wheels). Compilers, dev dependencies, and build caches stay in the discarded
build stage. For compiled languages the runtime can be `distroless` or `scratch`
+ a static binary — single-digit MB.

## Layer cache — order + atomic RUNs

- Order least-volatile → most-volatile: base → system packages → dependency
  manifest + install → source. A change invalidates its layer and all after it.
- One logical step per `RUN`, chained with `&&`, cleaning in the same layer:

```dockerfile
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*        # cleanup in the SAME layer or it still ships
```

Cleanup in a *later* `RUN` doesn't shrink the image — the earlier layer already
recorded the files. BuildKit cache mounts (`--mount=type=cache,target=/root/.cache`)
keep package caches across builds without baking them in.

## `.dockerignore` is not optional

```
.git
node_modules
**/*.log
.env
dist
```

The build context is tar'd and sent to the daemon; without `.dockerignore` it
includes `.git` (history!), local `node_modules`, and possibly `.env` secrets —
slowing the build and risking a leak. Mirror `.gitignore` plus build outputs.

## Measure

`docker build` shows per-step timing; `docker history <image>` shows per-layer
size — find the fat layer. `docker images` shows the total. A web app runtime
over ~250 MB usually means the build stage leaked into runtime, or no `-slim`.
