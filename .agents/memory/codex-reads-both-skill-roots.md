---
name: codex-reads-both-skill-roots
description: "Codex 0.164-0.171 loads repo skills from .codex/skills and .agents/skills, but skips a SKILL.md that is itself a symlink; probe with codex debug prompt-input."
metadata:
  node_type: memory
  type: reference
  originSessionId: 9ce9753f-dae9-468c-ae58-824973da3161
  modified: 2026-10-24T19:31:58.546Z
---

developers.openai.com/codex/skills lists only `.agents/skills` for repo scope, but
on codex-cli 0.164.0 a scratch repo with `.codex/skills/a` and `.agents/skills/b`
shows both in the model-visible skill list. So coding-os rendering skills into
`.codex/skills` is not broken (TASK-1064 closed with no change).

**How to apply:** before "fixing" a skill path, run
`codex debug prompt-input > out.json` in a scratch git repo and grep the probe
names — it renders the exact prompt input without a model call. Re-run it after
a Codex upgrade; same-named skills in two roots are listed twice, not merged.

**Symlinks (re-probed on 0.171.0, 2026-11-26):** a symlinked skill *directory*
is listed, a symlinked `SKILL.md` *file* is silently skipped. coding-os's own
`.codex/skills` used file links, so Codex saw none of its skills there
([harness-loading-audit-2026-11.md](../../docs/engineering/harness-loading-audit-2026-11.md) C1).
