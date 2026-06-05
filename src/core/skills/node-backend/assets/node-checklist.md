<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Node Backend Ship Checklist

Run before deploying a Node service.

## Event loop
- [ ] No `*Sync` fs/crypto/zlib on the request path.
- [ ] CPU-heavy work (hashing, parsing MBs, big loops) offloaded to a Worker / queue.
- [ ] Large payloads streamed (`pipeline`), not buffered.
- [ ] Loop-lag metric exported + alerted.

## Errors & lifecycle
- [ ] `process.on("unhandledRejection")` + `uncaughtException` → log + exit non-zero.
- [ ] Every async handler has an error path (Express 4 wrapper, or Express 5/Fastify).
- [ ] No empty `catch` blocks; errors handled or rethrown.
- [ ] Every outbound call has a timeout + AbortController cancellation.
- [ ] `Promise.all` over large arrays bounded (`p-limit`/batches).
- [ ] `SIGTERM`/`SIGINT` graceful shutdown: stop listener → drain → exit (with a cap).

## Build & deploy
- [ ] `engines.node` pinned to Active LTS.
- [ ] Lockfile committed; CI uses `npm ci` (not `install`).
- [ ] `python3 scripts/check_package.py package.json` → `clean`.
- [ ] Secrets from env/vault, never in code or image.
- [ ] `make skills-check-versions` — Node/framework pins current.
