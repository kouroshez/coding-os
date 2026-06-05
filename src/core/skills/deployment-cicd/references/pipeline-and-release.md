<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-06-04 -->
# Pipeline & Release — CI Stages, Deploy Strategies, Rollback

> P: Build a CI/CD pipeline that ships safely and rolls back fast.
> R: Designing CI, choosing a deploy strategy, or defining a rollback path.
> S: Container image craft — that's [docker](../../docker/SKILL.md). The host — [linux-sysadmin](../../linux-sysadmin/SKILL.md).
> N: [SKILL.md](../SKILL.md), [deploy-checklist.md](../assets/deploy-checklist.md)

> Nav: [Skill](../SKILL.md)

## CI stages (fail fast, cheapest first)

```
lint → typecheck → unit → build → integration → e2e → security scan → deploy
```

Order cheapest/fastest checks first so a lint error fails in seconds, not after a
10-minute test run. Cache dependencies; run independent stages in parallel. Pin
every action to a tag or SHA (`actions/checkout@v4`, not `@main`) —
`lint_workflow.py` flags moving refs, echoed secrets, and missing timeouts.

## Deploy strategies

| Strategy | How | Use when |
|---|---|---|
| rolling | replace instances batch by batch | default; some version overlap is fine |
| blue-green | stand up new env, flip traffic, keep old | instant rollback (flip back), needs 2× capacity briefly |
| canary | route a small % to the new version, watch, ramp | high-risk change; catch issues at 1% blast radius |

Blue-green gives the fastest rollback (flip the router back); canary gives the
smallest blast radius. Rolling is the simplest default. Whichever you pick, a
**rollback** must be one documented command — rollback is the most-used incident
action ([incident-response](../../incident-response/SKILL.md)).

## Versioning + release

Semantic versioning (`MAJOR.MINOR.PATCH`): breaking / feature / fix. Conventional
Commits drive automated changelogs + version bumps (release-please/semantic-release
parse the commit type). Tag the release; the image/artifact is immutable and
addressable by that tag — never re-deploy `latest`.

## Migrations + deploys (the ordering trap)

Schema migrations must be **backward-compatible** with the currently-running code,
because during a rolling deploy both versions run at once. Expand-then-contract:
add the new column/table (old code ignores it) → deploy code that uses it →
later, remove the old column. A migration that drops a column the old code still
reads takes the site down mid-deploy.

## Observability of the deploy itself

Emit a deploy marker to metrics so a latency/error regression can be correlated to
the release that caused it ([observability](../../observability/SKILL.md)). A deploy
you can't see in the dashboards is a deploy you can't safely roll back.
