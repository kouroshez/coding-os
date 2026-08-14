<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-11 -->
# Hub Threat Model — localhost trust boundary (TASK-363)

> SSOT for what the Hub trusts, what it defends against, and which control
> closes which threat. Companion to
> [hub-architecture.md § Localhost security gate](hub-architecture.md).

## Trust boundary

The Hub is a FastAPI singleton bound to `127.0.0.1:9188`, **never** a
non-loopback interface by default. It spawns `cos init` subprocesses and
writes `~/.coding-os/registry.json` plus project scaffolds — the highest-value
write capabilities on the machine it runs on.

| | |
|---|---|
| **Actors** | any local process/user reaching 127.0.0.1; malicious web pages driving the user's browser (CSRF, DNS rebinding) |
| **Assets** | filesystem writes via `name`/`parent_dir`; subprocess argv via `template`/`preset`/`agent`/`skills`; registry integrity; init job control |
| **Out of scope** | multi-user RBAC; network exposure (anyone who reverse-proxies the hub onto a network accepts that risk — set `COS_HUB_TOKEN` at minimum); secrets storage (the hub holds none) |

## Threats → controls

| Threat | Control | Where |
|---|---|---|
| CSRF from a drive-by page | double-submit `cos_csrf` cookie + `X-CSRF-Token` on mutations carrying browser evidence | `SecurityGateMiddleware` ([security.py](../../src/core/web/security.py)) |
| DNS rebinding (`evil.com` → 127.0.0.1) | Host/Origin allowlist (`localhost`, `127.0.0.1`, `::1`, + `COS_WEB_ALLOWED_HOSTS`) | `SecurityGateMiddleware` |
| Path traversal via project name | `^[a-z0-9][a-z0-9._-]{0,63}$` — no separators, no leading dot; target is always exactly one component under the validated parent | `_validate_init_inputs` ([hub.py](../../src/core/web/routes/hub.py)) |
| Scaffolding over sensitive trees | parent must exist, be writable, not the meta-repo, not inside a registered project; existing target → 409 | `_validate_init_inputs` |
| Argv injection into `cos init` | every subprocess argument validated against a registry (stacks, preset, agent, skills) — arbitrary strings never reach argv; fixed argv list, never `shell=True` | `_validate_init_inputs` + `_build_cos_init_cmd` |
| Unauthorized mutations (shared machines / reverse-proxied hubs) | optional `COS_HUB_TOKEN` → every state-changing `/api/*` request requires `Authorization: Bearer <token>` (401 otherwise, constant-time compare, applies even with the CORS dev escape) | `SecurityGateMiddleware` |
| Unauthorized **reads** of the whole code graph from a remotely-reachable hub | when `COS_HUB_TOKEN` is set AND the resolved `Host` is non-loopback (not in `_BASE_ALLOWED_HOSTS` = `localhost`/`127.0.0.1`/`::1`), read `GET /api/*` also requires the bearer (401 otherwise). Loopback reads stay open and byte-unchanged — the single-user dev default is unaffected (TASK-487) | `SecurityGateMiddleware` |
| Serving the API to the network with no credential at all | the process **refuses to start** when the bind host is off-loopback and `COS_HUB_TOKEN` is unset — the row above only engages once a token exists, so with none set an `0.0.0.0` bind previously answered everyone. Escape hatch `COS_HUB_ALLOW_INSECURE_BIND=1` (what `docker-compose.yml` uses, because there the published port, not the container interface, is the boundary) | `assert_bind_is_safe` ([security.py](../../src/core/web/security.py)), called from `create_app` |
| Runaway/hostile init job | job cancel terminates the subprocess and removes the partial scaffold; failed init rolls back; terminal jobs GC'd | [init_jobs.py](../../src/core/web/init_jobs.py) |
| Registry poisoning via scan | bounded scan (depth ≤ 6, ≤ 5000 dirs) + `.coding-os/` heuristic | hub.py scan route |

## Non-goals (explicit)

- The token is a **shared-machine / reverse-proxy hardening knob**, not an
  auth system — no users, no scopes, no rotation machinery (a future
  multi-user hub would replace it wholesale rather than extend it).
- No rate limiting on localhost mutations: the actor already runs code on
  the machine; throttling adds friction without a security win.
- Non-loopback detection trusts the `Host` header. A reverse proxy that
  rewrites `Host` to a loopback name (or forges `X-Forwarded-*`) can present
  as local; an operator placing the hub behind a proxy owns that proxy's
  config and must preserve the real `Host` (or set `COS_HUB_TOKEN` and treat
  the hub as authenticated regardless). The SPA bearer-on-reads client and a
  real remote-auth UX are deferred until a hosted hub is an actual launch
  decision — the server-side gate ships first to close the window.

## Regression coverage

`tests/test_hub_security_gate.py` (gate + token modes) and
`tests/test_hub_init_route.py` (traversal, allowlist, rollback) — both in the
web-route light suite; run on every hub change.
