---
id: TASK-105
title: "Harden danger/secret regex — rm -rf / · . · .. · * · -fr bypass, sk- false-positive, force-push refspec"
swimlane: core
kind: bug
epic: hook-remediation
labels: [safety, hooks, critical, audit-n2, ready]
status: complete
priority: P0
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-105: Harden danger/secret regex — rm -rf / · . · .. · * · -fr bypass, sk- false-positive, force-push refspec

**Outcome (one sentence):** block-dangerous-commands blocks rm -rf on /, ., .., *, ./, and flag-order variants (-fr, -r -f); force-push refspec (+main) caught; block-secrets sk- regex no longer false-fires on kebab slugs.

## Read First
- src/core/hooks/block-dangerous-commands.sh
- src/core/hooks/block-secrets.sh

## Repro Steps
1. Pipe `{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}` to block-dangerous-commands.sh → currently exit 0 (ALLOWED). Same for `rm -rf .`, `rm -rf ..`, `rm -rf *`, `rm -fr backend`.
2. Pipe a Write of a file containing `const sku = 'sk-product-identifier-some-long-internal-code-x'` to block-secrets.sh → currently exit 2 (false BLOCK).
Expected: dangerous rm blocked; kebab slug allowed.
Actual: trailing `\b` in the rm regex lets /·.·..·* through; the sk- char-class includes `-` so kebab strings match.

## Acceptance (G/W/T)
- **Given** a destructive `rm -rf` targeting root/cwd/parent/glob or a flag-order variant
- **When** block-dangerous-commands.sh inspects the Bash command
- **Then** it exits 2 (blocked); a force-push refspec `git push origin +main` is blocked; block-secrets no longer blocks kebab-case `sk-...` non-secrets; behavior tests cover each case; `make verify-hooks` passes.

## Work Log
- 2026-06-05 [claude]: N2 COMPLETE 2a-2d: rm -rf bypass closed via shlex helper (10d1240, 19 tests), force-push refspec blocked, sk- regex no k
