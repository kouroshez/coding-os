<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-07-16 -->
# Product Vision — coding-os

> **SSOT for the product's why and where.** Values live in [constitution.md](constitution.md); rules live in [critical-rules.md](critical-rules.md); this doc holds the destination those exist to reach. Update it when the strategy changes — never restate it in prompts.

## What coding-os is

An **agent-agnostic cognitive operating system** that sits as a layer above coding agents (Claude Code today; Codex, Gemini and others through adapters) and gives them what raw agent runtimes lack: persistent memory, a knowledge graph, a task board, role composition, and hard enforcement of engineering discipline. The kernel is hexagonal — core → adapters → templates — so agents, stacks, and modules can be added or removed without breaking the system.

## Where it is going

- **Enterprise-grade from day one.** No "quick now, proper later." Every consumer — solo beginner to large org — gets the same disciplined core, because the autonomy layer only works when its guarantees hold everywhere.
- **Community adoption as the north-star metric.** The aspiration is a top-tier open-source project for the AI-coding community (order of 100k GitHub stars); architecture quality and dogfood credibility are the growth engine, not marketing.
- **Current phase:** the Claude adapter is the priority; other adapters follow behind the parity contract (`adapter.yaml::hook_capabilities`).
- **Cross-adapter orchestration (roadmap):** the kernel learns to route work mid-task to the best runtime/model — delegate a subtask to Codex, a cheap mechanical pass to a smaller model, ops to another chain — building on the settings-gated [model-routing](../../src/core/rules/model-routing.md) seam. Capabilities available on one adapter get reimplemented globally in core when feasible, so every runtime inherits them.
- **Shape discipline:** the system evolves toward *fewer, denser parts* — the [Raptor consolidation lens](../architecture/raptor-consolidation.md) is the standing architecture-review standard.

## Operator contract — how agents engage with the human

The operator (project owner) explicitly requests these norms from every agent session:

1. **Challenge, never rubber-stamp.** If the operator's plan or a proposed design has a weakness, say so directly, with evidence and an alternative. Agreement without scrutiny is a defect.
2. **Adversarial self-review.** Before finalizing any non-trivial design, attack it as a hostile critic: blind spots, bottlenecks, failure scenarios. Summarize what the attack found.
3. **No claimed behavior without execution** (Critical Rule 26), and any web-sourced statistics must be verified current as of the day they are cited.

## See also

- [constitution.md](constitution.md) — the 8 values.
- [meta-project.md](../architecture/meta-project.md) — the DNA → mRNA → phenotype architecture.
- [raptor-consolidation.md](../architecture/raptor-consolidation.md) — the structural-evolution standard.
