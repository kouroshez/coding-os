<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-05-01 -->

# ADR-0004: Web Hub is a singleton FastAPI serving every registered project

- **Status:** Accepted (2026-05-01)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** web, multi-project, ports, devx

## Context

Each coding-os project has rich visualizable state: a knowledge
graph, a Scrumban board, a cognition trace, search across four
retrieval layers. The original design was **per-project port**
— every project booted its own FastAPI on a chosen port and you
opened the right URL.

Two problems emerged:

1. **Port management.** A user with five projects had five ports
   to remember + manage in browser tabs. Conflicts when two
   projects defaulted to the same port. Tooling to allocate ports
   added complexity.
2. **Cross-project context.** Looking at project A's graph and
   project B's board required two tabs. There was no obvious
   "switcher" — the UI assumed a single project.

## Decision

Singleton FastAPI on a fixed port (**9188**) that serves **every
registered project** via path-prefixed routes:

```
/                              → project picker / dashboard
/api/p/<slug>/graph            → project <slug>'s graph routes
/api/p/<slug>/board            → project <slug>'s board routes
/api/p/<slug>/cognition        → project <slug>'s cognition trace
/api/p/<slug>/search           → unified search across <slug>'s layers
/api/stream/events             → SSE event stream (multiplexed across projects)
```

Projects register themselves on `cos init` (writes a line to
`~/.coding-os/registry.json`). The hub discovers them at boot;
adding a new project is a matter of `cos hub status --refresh`
without a restart.

`cos hub start` boots the hub. `cos hub status` reports running
state + the meta-repo path + symlink health for every registered
project.

## Consequences

**Positive:**

- One URL to remember (`http://127.0.0.1:9188`).
- One process to manage (start/stop/restart).
- Side-by-side visibility across projects — the dashboard lists
  every registered project as a tile.
- Easier to share with a human collaborator on the same machine
  (port-forward one port instead of N).
- SSE event stream can fan out updates from any project to any
  subscriber.

**Negative:**

- One process means one crash takes down all projects' UIs.
  Mitigated by the lightweight FastAPI surface — no long-lived
  state, restart is sub-second.
- Path-prefix routes are slightly more verbose to write in
  frontend code (every fetch needs the slug). Mitigated by the
  `useProject()` React hook that hides the prefix.
- The fixed port (9188) can conflict with other tools. Mitigated
  by `COS_HUB_PORT` env var override + clear error message on
  EADDRINUSE.

**Mitigations / follow-ups:**

- The frontend SPA is built once and cached; the FastAPI just
  serves the static bundle + the per-project APIs.
- A future "embed mode" where the hub mounts inside a
  larger IDE-style shell is straightforward — it's already a
  separated FastAPI + React boundary.

## Alternatives considered

- **Per-project ports.** Original design. Rejected — see Context.
- **One FastAPI per project, fronted by a reverse proxy.**
  Adds operational complexity (configure nginx/Caddy) for no
  meaningful gain over the singleton.
- **No web UI; CLI-only.** Rejected — the graph and board are
  hard to read in a terminal at any nontrivial scale.
