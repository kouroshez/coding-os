<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-06-04 -->
# Compose Patterns — Healthchecks, Dependencies, Profiles

> P: Wire a multi-service local stack that starts in the right order and stays debuggable.
> R: Writing `compose.yaml` for local dev or integration tests.
> S: Production orchestration (k8s) — that's [deployment-cicd](../../deployment-cicd/SKILL.md).
> N: [SKILL.md](../SKILL.md), [dockerfile-optimization.md](dockerfile-optimization.md)

> Nav: [Skill](../SKILL.md)

## Wait for READY, not STARTED

```yaml
services:
  api:
    build: .
    depends_on:
      db: { condition: service_healthy }
  db:
    image: postgres:18
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
```

Plain `depends_on: [db]` only waits for the db container to *start* — the app
still races the database's own startup and crashes on "connection refused".
`condition: service_healthy` + a real `healthcheck` blocks the app until the db
answers. This single pattern removes most "works on the second `up`" flakiness.

## Profiles — optional services

```yaml
services:
  api: { build: . }
  mailhog:
    image: mailhog/mailhog
    profiles: ["dev"]        # only starts with: docker compose --profile dev up
```

Keep heavy optional services (mail catchers, admin UIs) behind a profile so the
default `up` is fast. Test-only fixtures go behind a `test` profile.

## Named volumes + networks

- **Named volume** for data that must survive `down` (`db-data:/var/lib/postgresql/data`);
  a bind mount for source you edit live. `docker compose down -v` wipes volumes — know which.
- Compose creates a default network; services reach each other by **service name**
  (`postgres://db:5432`), not `localhost`. Only `ports:` you actually need exposed
  to the host — internal services need none.

## Env + secrets

`environment:` for non-secret config; an `.env` file (git-ignored) for local
values via `${VAR}`. Never commit real secrets — for anything sensitive use
compose `secrets:` (file-backed) so it's mounted, not baked. Production secrets
come from the orchestrator's store, not compose.

## One command to reset

`docker compose down -v --remove-orphans && docker compose up --build` is the
clean-slate reset — fresh volumes, rebuilt images, no stale orphan containers.
Document it so "it's broken locally" has a known cure.
