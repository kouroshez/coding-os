<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-14 -->

# ADR-0007: GUI-first install path — boot the Hub before any CLI setup

- **Status:** Accepted (2026-06-14, TASK-390)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** onboarding, hub, install, security, localhost-trust

## Context

The documented entry point ([README § Quickstart](../../../README.md)) assumes a
developer already ran `uv tool install --editable .` and reached a shell. A
GUI-first user — someone who wants to *see* the Hub and the onboarding wizard
before learning any command — has no path: there is no `cos` binary yet, so
there is nothing to type. We need a single command that takes a bare machine to
the wizard at `http://127.0.0.1:9188` with no prior CLI step.

Two facts shape the decision:

1. **The Hub already binds localhost.** `cos hub start`
   ([src/cli/hub_commands.py](../../../src/cli/hub_commands.py)) and the Docker
   image both serve on `127.0.0.1:9188` / `0.0.0.0:9188`-inside-container.
   No new server, port, or process model is introduced here.
2. **Two prerequisite checks already exist.** `cos doctor --bootstrap`
   ([src/cli/doctor.py](../../../src/cli/doctor.py) → `run_bootstrap_doctor`)
   verifies python/bash/git/uv/sed with no initialized project, and the auth
   posture (`COS_HUB_TOKEN` bearer mode) is already implemented in
   `SecurityGateMiddleware` ([TASK-363](../../engineering/hub-threat-model.md)).

The trap to avoid is inventing a second, divergent boot path — a bespoke daemon,
a new port, or a parallel auth scheme — that drifts from the CLI/Docker truth.

## Decision

**Ship two GUI-first one-liners that converge on the existing
`cos hub start` localhost server; add no new server, port, or auth scheme.**

### 1. Localhost-bind by default

Both paths bind the Hub to `127.0.0.1:9188` (the container publishes the same
port). The default trust boundary is "whoever is on this machine" — correct for
the single-user laptop that GUI-first onboarding targets, and identical to the
posture every other entry point already assumes
([hub-threat-model.md](../../engineering/hub-threat-model.md)).

### 2. Optional auth token reused from TASK-363

When `COS_HUB_TOKEN` is set, the installer exports it into the Hub process; the
existing `SecurityGateMiddleware` then requires `Authorization: Bearer <token>`
on every mutating `/api/*` request (reads stay open, constant-time compare). No
new auth code — the installer is a *transport* for the token, not a new
mechanism. A user who reverse-proxies the Hub onto a network sets this; the
default (unset) keeps open-localhost.

### 3. A Docker one-liner and a native installer

- **Docker:** `docker compose up` (already shipped — [Dockerfile](../../../Dockerfile),
  [docker-compose.yml](../../../docker-compose.yml)) builds the SPA, installs
  the package, and runs `cos hub start --foreground` on 9188. This ADR adopts it
  as the canonical zero-prereq path; nothing new is built for it.
- **Native:** [install.sh](../../../install.sh) at the repo root, runnable as
  `curl -fsSL …/install.sh | bash` or `bash install.sh` from a checkout. It
  preflights bash/git/uv (installing uv if absent), runs `uv tool install`,
  re-verifies via `cos doctor --bootstrap`, then `cos hub start`. The script
  honors `COS_HUB_PORT` and `COS_HUB_TOKEN`.

## Consequences

**Positive:**

- A GUI-first user reaches the onboarding wizard with one command and no prior
  CLI knowledge.
- Both paths converge on the *same* localhost server, the *same* bootstrap
  doctor, and the *same* auth middleware — zero behavioral drift, nothing new to
  keep in sync.
- The auth posture is opt-in and inherited verbatim from TASK-363; the secure
  default (localhost-only) needs no flag.

**Negative / deferred:**

- The native installer assumes outbound network (to clone the repo and fetch uv)
  — air-gapped installs use the Docker image or a pre-seeded checkout instead.
- Where the meta-repo lives is the installer's choice (`$HOME/.coding-os-src`
  when run via `curl | bash`, or the current checkout); a future move requires
  `cos sync-doctor --repair` exactly as a manual move does today — no new
  relocation logic is added here.
- Network exposure beyond localhost remains the operator's responsibility
  (`COS_HUB_TOKEN` is the minimum control); this ADR does not add TLS or RBAC.

## Alternatives considered

- **A bespoke GUI-launcher daemon.** Rejected — it would be a second server to
  maintain, drifting from `cos hub start` and the Docker image. The seam already
  exists; wrap it, do not fork it.
- **Bind `0.0.0.0` by default for "easier" remote access.** Rejected — it
  silently exposes a write-capable API to the network. Localhost-default +
  opt-in `COS_HUB_TOKEN` is the safe posture; an operator who needs remote
  access makes that trade-off explicitly.
- **A new installer-only auth scheme (basic auth, generated password).**
  Rejected — TASK-363 already shipped a constant-time bearer-token gate. A second
  scheme would split the surface and the threat model for no gain.
