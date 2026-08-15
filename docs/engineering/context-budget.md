<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-15 -->
# Context Budget — what coding-os costs before it saves anything

Purpose: State, per project profile and from measurement, how many tokens the
always-on instruction layer occupies — so every savings claim elsewhere in the
docs can be read net of what the system charges to be present.
Read when: publishing a token number, adding a rule, or answering "what does this
cost me".
Skip when: the change touches neither the rule set nor a published benchmark.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## The claim this file exists to prevent

A retrieval layer that saves tokens on queries but charges a fixed toll on every
turn has a *net* effect, not a gross one. Publishing only the gross saving is the
oldest trick in benchmark writing, and it is the first thing a skeptical reader
checks. This file is the toll.

## What "always-on" means

Loaded on every turn regardless of what the agent does:

| Layer | Always-on? | Why |
|---|---|---|
| `CLAUDE.md` / `AGENTS.md` | **yes** | the runtime injects it into every request |
| `.claude/rules/*.md` | **yes** | same |
| `.claude/skills/**` | no | loaded by the `Skill` tool, on demand, per matching glob |
| `.claude/commands/**` | no | loaded when the slash command is invoked |
| MCP tool schemas | no on Claude, yes on runtimes without deferred tools | Claude Code fetches schemas through `ToolSearch`; only names are resident |
| `.claude/hooks/**` | no | separate processes; never enter the model's context |

Counting the skills or hooks directory toward context cost inflates the number by
an order of magnitude. A scaffold writes ~370 files; **8 to 12 of them are ever in
context.**

## Measured budgets

Regenerate with:

```bash
uv run python src/scripts/context_budget.py                 # representative span
uv run python src/scripts/context_budget.py --all-presets   # every preset
```

The profiler runs the real `cos init` for each preset into a temp dir, then sums
the characters of the root instruction file and the rules directory. Tokens are
`characters / 4` — the same heuristic the graph envelopes report, and it is an
estimate, not a tokenizer.

<!-- BEGIN context-budget-table -->
Measured 2026-08-15, all 21 presets, `coding-os` 0.3.19:

| Profile | Stacks | Root | Core rules | Stack rules | **Always-on total** | Share of a 200k window | Skills on disk (lazy) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `t3-style` | nextjs | 3,238 | 9,266 | 199 | **12,704** | 6.4% | 46 |
| `nuxt-fullstack` | vue-nuxt | 3,173 | 9,266 | 286 | **12,726** | 6.4% | 46 |
| `wordpress-cms` | wordpress | 3,195 | 9,266 | 277 | **12,738** | 6.4% | 46 |
| `tall` | laravel | 3,179 | 9,266 | 320 | **12,765** | 6.4% | 46 |
| `jamstack` | astro | 3,238 | 9,266 | 328 | **12,833** | 6.4% | 46 |
| `flutter-baas` | flutter | 3,181 | 9,266 | 465 | **12,913** | 6.5% | 46 |
| `rails-react` | rails, nextjs | 3,370 | 9,266 | 346 | **12,982** | 6.5% | 47 |
| `ai-saas` | nextjs, fastapi | 3,333 | 9,266 | 414 | **13,014** | 6.5% | 47 |
| `nextjs-fastapi` | nextjs, fastapi | 3,335 | 9,266 | 414 | **13,016** | 6.5% | 47 |
| `django-next` | django, nextjs | 3,358 | 9,266 | 396 | **13,021** | 6.5% | 47 |
| `mean` | node-express, angular | 3,318 | 9,266 | 556 | **13,141** | 6.6% | 47 |
| `nest-angular` | nestjs, angular | 3,326 | 9,266 | 559 | **13,152** | 6.6% | 47 |
| `go-react` | go-fiber, nextjs | 3,350 | 9,266 | 536 | **13,153** | 6.6% | 47 |
| `mern` | node-express, nextjs | 3,355 | 9,266 | 536 | **13,158** | 6.6% | 47 |
| `pern` | node-express, nextjs | 3,355 | 9,266 | 536 | **13,158** | 6.6% | 47 |
| `laravel-vue` | laravel, vue-nuxt | 3,286 | 9,266 | 606 | **13,159** | 6.6% | 47 |
| `rn-api` | react-native, fastapi | 3,278 | 9,266 | 628 | **13,172** | 6.6% | 48 |
| `dotnet-react` | aspnet-core, nextjs | 3,394 | 9,266 | 567 | **13,227** | 6.6% | 47 |
| `spring-react` | spring-boot, nextjs | 3,380 | 9,266 | 617 | **13,264** | 6.6% | 47 |
| `rust-svelte` | rust-axum, svelte-sveltekit | 3,368 | 9,266 | 744 | **13,379** | 6.7% | 47 |
| `hexagonal-product` | go, go-fiber, fastapi, react-native | 3,534 | 9,266 | 1,171 | **13,972** | 7.0% | 50 |

**Read the spread, not an average.** The whole 21-preset range is **12,704 to
13,972 tokens — 6.4% to 7.0%** of a 200k window. A four-stack polyglot pays 1,268
tokens more than a single-stack CMS, because the per-stack rules are 199–1,171
tokens each and everything else is shared.

The dominant term is **9,266 tokens of stack-agnostic core rules, identical for
every profile**. If the always-on budget is ever to come down meaningfully, that
is the only place with enough mass to matter — not the stack overlays.

Note the last column: 46 to 50 skills sit on disk and **none of them are in
context**. A scaffold writes ~370 files; 8 to 12 enter the prompt.
<!-- END context-budget-table -->

### This repo, for contrast

| Profile | Root | Core rules | Stack rules | **Always-on total** | Share of 200k |
| --- | ---: | ---: | ---: | ---: | ---: |
| `coding-os` (meta) | 3,934 | 14,270 | 1,773 | **19,977** | 10.0% |

## Why the meta-repo is not a consumer number

This repo (`coding-os` itself) carries two rules files no consumer receives:
`dimension-registry.md` and `skill-enforcement.md` are generated from **every**
installed stack, and the meta-repo installs all of them. It also carries four
`meta-*` rules that only apply to work on the kernel. Measuring this repo and
publishing the result as the consumer cost overstates it by roughly a factor of
two. Any figure quoted publicly must come from the profiler's preset runs.

## Empirical cross-check

The estimate above is a static file measurement. The runtime figure comes from
agent transcripts, where the first assistant turn of a session carries the whole
resident prefix:

```bash
cos doctor --tokens --tokens-days 30
```

Across 132 sessions in this repo the median first-turn context was **58,446
tokens**. A project with a ~6 KB instruction file measured **38,972**, which puts
the Claude Code floor — system prompt plus resident tool schemas, before any
project instruction — near **37,000 tokens**. The difference tracks the static
estimate closely enough to trust the method, and it also means the honest
denominator for "what fraction of my window is coding-os" is the *delta*, not the
whole first-turn figure.

## The cost that is not tokens

Prompt caching makes the dollar cost of the always-on layer small: measured over
73,898 turns in this repo, **99.1%** of input tokens were cache reads, billed at a
fraction of the base rate. The prefix is written once per session and read cheaply
thereafter.

What caching does **not** buy back is instruction adherence. The published
evidence is that following degrades as instruction density rises, with a bias
toward instructions that appear earlier — see
[IFScale](https://arxiv.org/abs/2507.11538) (20 models; even frontier models reach
only 68% adherence at 500 concurrent instructions, with reasoning models showing
"threshold decay": near-perfect until a critical density, then a steeper slope) and
[ManyIFEval](https://openreview.net/forum?id=R6q67CDBCH).

This project has **not** measured its own position on that curve. Until
[TASK-985](../tasks/) reports which rules actually fire, "28 critical rules is
fine" is an assumption, not a finding. Treat the rule count as a budget to defend,
not a feature to grow.

## Rules for anyone adding to the always-on layer

1. A new always-on rule must name what it prevents that no existing rule does.
2. Prefer a skill (lazy, glob-scoped) over a rule (resident) whenever the guidance
   applies to a file type rather than to every turn.
3. Regenerate the table in this file in the same commit as any change to
   `src/core/rules/**` or a stack's `rules/`.

## See also

- [third-party-token-bench.md](third-party-token-bench.md) — the savings side of
  the ledger, and the harness that must net it against this cost.
- [test-governance.md](test-governance.md) — the same measure-before-asserting
  discipline applied to suite runtime.
- `src/scripts/context_budget.py` — the profiler.
