<!-- domain:META | layer:reference | ssot:true | updated:2026-06-19 -->

# Stack Maturity Matrix

> P: SSOT for how mature each shipped stack template actually is — the honest answer to "is this stack production-ready?", separating breadth (how many stacks exist) from depth (how many are validated). Closes the claim-vs-maturity gap (strategic-audit 2026-06, report §S3).
> R: Before claiming stack coverage in marketing/docs, before promoting a stack, or when deciding whether to add a new stack vs deepen an existing one (report §S4 depth-over-breadth).
> S: You only need the count of stacks — that is `ls src/templates` minus the infra dirs (`_base`, `_presets`, `meta`).
> N: [docs/engineering/doc-system-overhaul-roadmap.md](../engineering/doc-system-overhaul-roadmap.md), [docs/playbooks/template-authoring.md](../playbooks/template-authoring.md), [docs/architecture/adr/0010-consumer-distribution-version-gate.md](../architecture/adr/0010-consumer-distribution-version-gate.md)

> Nav: [Governance Index](./) | [Docs Index](../00-index.md)

## Why this exists

Coding OS ships many stack templates. Stack *count* is the wrong headline metric: a
stack that nobody has validated end-to-end is a liability, not a feature — an agent
will trust its scaffold and conventions, and if they are wrong the loop bakes drift
into a real consumer project. The strategic audit found the repo claimed broad
coverage while only a handful of stacks had any automated validation. This matrix
is the truthful breakdown, and a test (`tests/test_stack_maturity.py`) re-derives it
from ground truth so the doc cannot silently drift.

**Maturity is earned, not declared.** A stack does not get to call itself "stable"
in its own `stack.yaml`; it earns the tier by what objectively exists in the repo.
That is why the tier is *derived* from three signals rather than a hand-set field
(which can lie and rots): the audit's "add a `maturity:` field" prescription was
deliberately rejected in favor of derivation.

## Tier definitions (the derivation rule)

| Tier | Earned by (objective signal) | What it means for a consumer |
|---|---|---|
| **Stable** | A golden fixture exists at `tests/golden/claude_<stack>` — i.e. the full render is captured and parity-tested in CI | Scaffold + adapter render are validated; safe to build on. |
| **Beta** | A full framework overlay (`stack.yaml` with dimensions + skills + scaffold) but **no** golden fixture | Usable, but the render is unverified — review the scaffold before trusting it. |
| **Stub** | Named `*-plain` — a language-only skeleton (no framework opinion, minimal overlay) | A starting point only; expect to author conventions yourself. |

Infra directories under `src/templates/` are **not stacks** and are excluded from
this matrix: `_base` (shared base overlay), `_presets`, and `meta` (this repo's own
dogfood stack).

## The matrix (26 stacks)

Derived 2026-06-19; the test is the SSOT — if this table and the test disagree, the
test wins and this table is stale.

### Stable — 4 (golden-validated)

`django` · `nextjs` · `node-express` · `vue-nuxt`

### Beta — 16 (full overlay, not yet golden-validated)

`angular` · `aspnet-core` · `astro` · `fastapi` · `flutter` · `go` · `go-fiber` ·
`laravel` · `nestjs` · `python` · `rails` · `react-native` · `rust-axum` ·
`spring-boot` · `svelte-sveltekit` · `wordpress`

### Stub — 6 (`*-plain` language skeletons)

`csharp-plain` · `go-plain` · `java-plain` · `ruby-plain` · `rust-plain` ·
`typescript-plain`

## Positioning consequences (read before claiming coverage)

- **Headline honestly.** "27 stacks" is true but misleading. The honest line is
  "4 validated stacks, 16 in beta, 6 language skeletons." Marketing copy and the
  Hub should reflect tier, not raw count.
- **Depth over breadth (report §S4).** Do **not** add a new stack while 16 betas
  lack golden validation. The cheapest, highest-trust improvement is promoting a
  beta to stable by adding its golden fixture — not minting stack #27.
- **The promotion path is mechanical.** Add `tests/golden/claude_<stack>` (and the
  codex twin where applicable) via `make golden-capture SECTION=<id>`, confirm
  `tests/test_golden_parity.py` is green, and the stack auto-promotes to Stable in
  this matrix on the next derivation — no edit to this doc's logic required.

## Drift guard

`tests/test_stack_maturity.py` re-derives the three sets from the filesystem and
asserts this document lists exactly those stacks per tier. Adding, removing,
renaming, or golden-validating a stack without updating this table fails that test.
This is the same anti-drift contract that the stack-count lint enforces for the
"N stacks" literals in `AGENTS.md` (audit group A / TASK-461).

## See also

- [docs/playbooks/template-authoring.md](../playbooks/template-authoring.md) — how to author / promote a stack.
- [docs/engineering/doc-system-overhaul-roadmap.md](../engineering/doc-system-overhaul-roadmap.md) — the `stack-coverage` epic this matrix governs.
- Memory `strategic-audit-2026-06` — the audit that produced this matrix.
