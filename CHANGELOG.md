# Changelog

All notable changes to coding-os are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Development began in April 2026 and the full history is preserved in
> this repository. Release automation (release-please) starts at the
> [0.3.0](#030--2026-05-20) baseline below; entries before the first
> tagged release were written by hand and describe the project *as it
> was on that date* — the current adapter/parity state lives in
> [docs/engineering/adapter-parity.md](docs/engineering/adapter-parity.md).

## [0.3.5](https://github.com/kouroshez/coding-os/compare/v0.3.4...v0.3.5) (2026-08-06)


### Added

* **adapters:** complete Codex SDK and hook parity ([c19da47](https://github.com/kouroshez/coding-os/commit/c19da47e744f5beb36f6dda33dc9f0460eee55a4))
* **adapters:** dual Claude auth mode — subscription OAuth or API key, selectable in Hub panel ([4ab069e](https://github.com/kouroshez/coding-os/commit/4ab069ed927126092adb601a7ca6467e605f7910))
* **adapters:** refresh Codex SDK and hook parity ([5687d87](https://github.com/kouroshez/coding-os/commit/5687d871fac62f089ff99fa95e2fd98e80ced1a7))
* **adapters:** versioned agent memory — in-repo .agents/memory with self-repairing harness symlink ([5ede970](https://github.com/kouroshez/coding-os/commit/5ede9704cdf0067d650fc1ff231259f0a515b18f))
* **board:** autonomy-gated auto-commit of board↔git drift + fix silent drift-task filing ([14e9c99](https://github.com/kouroshez/coding-os/commit/14e9c9938f3f0ff2bf644b14d566dcc1d485c60d))
* **board:** blocked-lane SLA aging via blocked_sla_hours knob (observability only) ([9848b4d](https://github.com/kouroshez/coding-os/commit/9848b4d2c265d5cf0124cc3491d0341f348c6877))
* **board:** graduated DoD acceptance gate at complete + fix for_kind merge clobber ([2e3904e](https://github.com/kouroshez/coding-os/commit/2e3904e6c77abaa4e977e1cbedcb3555e2e65f44))
* **board:** hook-block trend KPI in cos retro (blocks/session vs prior period) ([ac8a855](https://github.com/kouroshez/coding-os/commit/ac8a8552f2069a475da9ad248bec35b9b21e51a4))
* **board:** warn on session-created un-ready icebox cards (create-then-park nudge) ([d5955b9](https://github.com/kouroshez/coding-os/commit/d5955b9ad441a8cd313b697b8a9721d635f8b2b7))
* **cli:** --enable-module escape from profile+disable union on init/adopt ([c400a40](https://github.com/kouroshez/coding-os/commit/c400a40602bdd1282a6ce2e5358fffb87c7ab32d))
* **cli:** add owner-gated brain-sweep-changelog to retire legacy changelog rows ([40fe6ad](https://github.com/kouroshez/coding-os/commit/40fe6adab974fc486b099567aa1b9408280faaa0))
* **cli:** generate backend Dockerfiles at init — render_dockerfile, cicd-gated ([0caf609](https://github.com/kouroshez/coding-os/commit/0caf609c2f6bea25f46affa17aefcc05132d4082))
* **cli:** generate consumer CI workflow at init — render_ci_workflow, cicd-gated ([484fa77](https://github.com/kouroshez/coding-os/commit/484fa77dd687e3f4e963c159fc431b08f7787116))
* **cli:** mention --preset in the interactive stack prompt ([c937049](https://github.com/kouroshez/coding-os/commit/c937049eb71c6534bace86ae6245ac094f80ca71))
* **cli:** stack-lint v2 soft checks + factory rows 13-18 + 4 backfilled rules ([f9c1824](https://github.com/kouroshez/coding-os/commit/f9c18240409211a3b27682858d822c9dd37ccad4))
* **cognition:** persist sub-agent transcript + cos cognition log --transcript ([52f116d](https://github.com/kouroshez/coding-os/commit/52f116d3a88cdf987492d3989c661ad0c2483849))
* **core:** doctor rule_drift + doc_drift audit + Hub drift banner (F-D) ([ea0a283](https://github.com/kouroshez/coding-os/commit/ea0a2837153412552b04c2d7da0137e235c6f1c3))
* **core:** JIT convention-rule reminders via jit-recall glob map (jit-rules.tsv) ([2bb8a3b](https://github.com/kouroshez/coding-os/commit/2bb8a3bb7bb6c644edda09aa659a01c42e07744d))
* **core:** live agent pip on task cards — pulse while the bound session works, click opens its chat ([433447b](https://github.com/kouroshez/coding-os/commit/433447b9bec4b4bec9b25f99e8d91412ae694188))
* **core:** live-toggle doc prune/restore + correct doc_drift source mapping (F-B) ([ea46554](https://github.com/kouroshez/coding-os/commit/ea465545a544c90235aba34397d6f6edb0653692))
* **core:** LLM friction-lesson distiller behind the dispatcher port (idempotent, budget-capped) ([3f0cd19](https://github.com/kouroshez/coding-os/commit/3f0cd199cdba66bfe9e83f4796170439113ee32b))
* **core:** module-owned rules — cascade-unlink a disabled module's rules (F-A) ([7c3620a](https://github.com/kouroshez/coding-os/commit/7c3620a5fd292c5c467962c9cb57b76f5ea05f12))
* **core:** out-of-core module overlay so a plugin registers a module without forking (F-F) ([b53ae18](https://github.com/kouroshez/coding-os/commit/b53ae18201fab62cbaf85d589fa5445c44eec20a))
* **core:** promotion ladder — promoted lessons leave belief surfaces; retro drafts rule promotions ([dd8736c](https://github.com/kouroshez/coding-os/commit/dd8736c7f7b66b413e57906f0f7cbe6bdbd36899))
* **core:** settings-gated board auto-spawn — drag icebox-&gt;in_progress dispatches an implementer ([01870c8](https://github.com/kouroshez/coding-os/commit/01870c88517d431ded45306192b6dc015febc7f5))
* **cost:** dispatch cost analytics + budget ladder; fix budget spent-today query ([a930cbe](https://github.com/kouroshez/coding-os/commit/a930cbe30c84736143884c6dffd4749afd03310d))
* **dispatch:** cost-routed multi-model dispatch — bandit, cheaper reviewer, adapter hint ([eb193f8](https://github.com/kouroshez/coding-os/commit/eb193f8caa3254b51dea1ca30a586e9033fd4d9e))
* **dispatch:** per-chain budget ceiling, EvidenceBundle flock, max_turns hop-cap ([2aaa2ec](https://github.com/kouroshez/coding-os/commit/2aaa2ecd0f6cdc52eff224b685cf928fbf2e831a))
* **docs-lint:** audit all root *.md and resolve link targets case-exactly ([339e445](https://github.com/kouroshez/coding-os/commit/339e4454e7e95ba142f3bc25d5870f6c9f970a10))
* **docs:** lint scaffold docs for untagged module-owned slash commands (F-H) ([f2c2d26](https://github.com/kouroshez/coding-os/commit/f2c2d26f9c720dd2f38f4634668924bd57b0adf3))
* **governor:** dedup make-target verify suites, not only bare pytest ([7a57b20](https://github.com/kouroshez/coding-os/commit/7a57b20373e2a93d16c683bbce26f98f7f64481f))
* **hooks:** nudge-git-mode + banner git=pr field so pr-mode is surfaced proactively ([ca63cab](https://github.com/kouroshez/coding-os/commit/ca63cabdafc4f6e25fa450240e0ca52905665276))
* **hooks:** nudge-reentry UserPromptSubmit reminder for an unbound in_progress task ([f99f800](https://github.com/kouroshez/coding-os/commit/f99f8005d85170ea2fc3b40dca64483125fe1df9))
* **hooks:** warn-diff-size nudges diff-minimal commits (fail-open) ([8c7a855](https://github.com/kouroshez/coding-os/commit/8c7a8558d78f0ee49ace8fdb45b11362c0cfa8fd))
* **hub:** add Config Adapters tab with runtime, models, and MCP wiring ([7fdf847](https://github.com/kouroshez/coding-os/commit/7fdf8476e4d772480de6aa78ffd77646ee1e4202))
* **hub:** add Marketplace top-nav tab (Extension Manager coming-soon) ([a2113a9](https://github.com/kouroshez/coding-os/commit/a2113a9c0a0c192a77da4d1147ec9067f9f2f1dc))
* **hub:** config stack/adapter/MCP install-remove endpoints (meta-guarded) ([3920fcf](https://github.com/kouroshez/coding-os/commit/3920fcfb408e892a90a378bebaf599dddd1578d5))
* **hub:** consolidate IA — Settings into Config, Memory into Workspace, slim Diagnostics ([233cade](https://github.com/kouroshez/coding-os/commit/233cade9bd0269a04aee784f75f05ab8f2b59e58))
* **hub:** declutter task HISTORY — commits-first default, details behind a toggle ([4732d29](https://github.com/kouroshez/coding-os/commit/4732d29c3e36788a6ac6a5d19a9691398828f058))
* **hub:** live dispatch observability via trace tee, SSE tail route, and chat fallback ([bb36dcb](https://github.com/kouroshez/coding-os/commit/bb36dcb1cbde6e98605f443881b59159b6b81485))
* **hub:** mark installed adapters in /api/config/adapters ([9e7dc6c](https://github.com/kouroshez/coding-os/commit/9e7dc6c59e26c0c82b6194e75fd40d5a3775f9cc))
* **hub:** Memory tab — validation-rate headline, tier groups, lesson evidence ([1e4aa20](https://github.com/kouroshez/coding-os/commit/1e4aa20c8833d2633f40259bb4b41b7b72f6063e))
* **hub:** ModulesTab discloses commands/rules + inline refusal reason + dependency why (F-E) ([0e0f8a9](https://github.com/kouroshez/coding-os/commit/0e0f8a9eab4e22d20725a5f87d476191dc7cf259))
* **hub:** move Overview into Workspace and restore the Design tab ([70c494c](https://github.com/kouroshez/coding-os/commit/70c494cabad9c24e0ea87aa816b70e9fd1ea4ed9))
* **hub:** redesign Config tabs — installed-first stacks, grouped skills, adapter/MCP add-remove ([b13f009](https://github.com/kouroshez/coding-os/commit/b13f009be01d8e44bd42db076c5b06fecc49edf8))
* **hub:** SettingsPage single-save flow — bottom Save flushes scheduled edits (TASK-836) ([9d5dc0d](https://github.com/kouroshez/coding-os/commit/9d5dc0d1627f7cda5c284df517aba29ebbd0461d))
* **hub:** show module reverse-deps + skills; pre-empt a blocked disable in Config ([4eb31bb](https://github.com/kouroshez/coding-os/commit/4eb31bb69889005a9a3f30ffa13d14d8a6048a30))
* **hub:** tag presets with provenance and clarify the composer preset choice ([1123d4a](https://github.com/kouroshez/coding-os/commit/1123d4ab73d12103a0f6bd2ce694798321647fe8))
* **hub:** typecheck every SPA API path against the generated OpenAPI types ([87f44f2](https://github.com/kouroshez/coding-os/commit/87f44f207e54470ab26dba685ca7f9ef8351dfb8))
* **learning:** derive per-task reward label from the verify ledger (v52) ([d9a18c7](https://github.com/kouroshez/coding-os/commit/d9a18c7ba9a98d27e70028083ccb19e7b177da60))
* **learning:** fire the validation loop for formal tasks + honest trust deflation ([0e01cd5](https://github.com/kouroshez/coding-os/commit/0e01cd549bd62c52004f4e3987cad69f715e48cc))
* **memory:** async per-session LLM enrichment of changelog observations (default-OFF) ([9d0fd0b](https://github.com/kouroshez/coding-os/commit/9d0fd0bf2660b6750cbb9ab867dbf19dba2da450))
* **memory:** fidelity-gated session_summaries.learned via apply_session_facts ([3c8358f](https://github.com/kouroshez/coding-os/commit/3c8358fa59cde0cb33ae2a419fe17b32b7ad8ba1))
* **memory:** MMR diversity + column-weighted FTS5 + RRF fusion in cos_search ([71582f8](https://github.com/kouroshez/coding-os/commit/71582f81b2bd2fa02c9cc7ed9181f1226615b914))
* **memory:** wire expires_at forward — TTL stamp at capture + decay GC of expired rows ([b4afa53](https://github.com/kouroshez/coding-os/commit/b4afa53de91b418d22d5e0a8b35e01cc86a88188))
* **modules:** lite install profile + per-module hint discovery in Hub ([123d180](https://github.com/kouroshez/coding-os/commit/123d180755f5c1c664347d196fe479f2679e6f5b))
* **pr:** bootstrap worktree gitignored deps + secrets so first validate works ([32ff02d](https://github.com/kouroshez/coding-os/commit/32ff02dd34495e837d11aadc59bde50bb47fe74c))
* **pr:** cos pr triage — ranked digest of open agent PRs for the review bottleneck ([ff34f0f](https://github.com/kouroshez/coding-os/commit/ff34f0fca50d03cd592fe06dc53bbc3a5b711998))
* **pr:** local_autonomous rung — cos pr land merges to local integration, guard-carved ([9813db5](https://github.com/kouroshez/coding-os/commit/9813db5e4a1daef89528750d49b8fb1c95f12e2a))
* **pulse:** surface last verify-suite result in the agent pulse ([5d97005](https://github.com/kouroshez/coding-os/commit/5d97005eaf4391f82593f9fd3429ae5d6bc8651a))
* **repair:** budget-capped autonomous repair loop + dispatchable repairer ([5b51ef5](https://github.com/kouroshez/coding-os/commit/5b51ef53b1dd2bf8dc56df4db9bfbebfb50413d6))
* **routing:** flag-gated Thompson-sampling Beta-Bernoulli model router ([f36abf5](https://github.com/kouroshez/coding-os/commit/f36abf5a400030dce1b59a7148005c9085476228))
* **stack-lint:** flag a shipped sample test that verify never runs ([34f5999](https://github.com/kouroshez/coding-os/commit/34f5999e226e4d5bdc4135ded9c264d1bbb013f4))
* **templates:** add famous-stack presets mern, nuxt-fullstack, laravel-vue, go-react ([6ff62fc](https://github.com/kouroshez/coding-os/commit/6ff62fc4ccf40b7c756cf779f2d36a9102591833))
* **templates:** bootable fastapi + django scaffolds (manifest, entrypoint, test, verify) ([a61ea1a](https://github.com/kouroshez/coding-os/commit/a61ea1a2680cc0fe9dc161061cafb75d6b3d7252))
* **templates:** bootable go + go-fiber scaffolds (go.mod, cmd/api entrypoint, test, verify) ([ad49864](https://github.com/kouroshez/coding-os/commit/ad49864dc540eb6d6aeb5008ef09c02918add5d7))
* **templates:** bootable nextjs + react-native seeds + flat ESLint migration ([d6d27d5](https://github.com/kouroshez/coding-os/commit/d6d27d59fa5add065009a2360032cdc6fd5bd256))
* **templates:** bootable wordpress php seed (composer.json + phpcs PSR-12) ([d7e952e](https://github.com/kouroshez/coding-os/commit/d7e952ed64542a684d114ac0ad50476bbddc63d3))
* **templates:** bump astro scaffold to v7 with the Content Layer API ([50a9feb](https://github.com/kouroshez/coding-os/commit/50a9feb28e221d1e8fe4933e515569e82a07d494))
* **templates:** language config bundle for go/rust/ruby/php/dart linters ([6448f45](https://github.com/kouroshez/coding-os/commit/6448f4508645f5d0fdf4b3e09b3380ea726af438))
* **templates:** migrate angular scaffold to v22 with Vitest unit-test runner ([f15bdea](https://github.com/kouroshez/coding-os/commit/f15bdea482bb0906d3b18f6a1ee6c73ed605ac90))
* **templates:** per-language toolchain config bundle selected by stack language ([b93307f](https://github.com/kouroshez/coding-os/commit/b93307f1a83bf3af6385fd584a4e812fbcce16a2))
* **templates:** seed .editorconfig + base .gitignore in _base/scaffold ([9d34998](https://github.com/kouroshez/coding-os/commit/9d34998bd1a18e1726e8507aa880e8c9582bb5d7))
* **verify:** add test-web-ui (vitest) suite + make ui-test target ([a65afee](https://github.com/kouroshez/coding-os/commit/a65afee3fe1b5061d3bc53f35ef6548b07534fca))


### Fixed

* **adapters:** add Sonnet 5 / Fable 5 to Claude model catalogue, bump SDK to 0.2.110 ([1cfad5b](https://github.com/kouroshez/coding-os/commit/1cfad5bc23dac37cdf9aa838da7c9ecb722c7709))
* **adapters:** drop codex delegates pointing at removed core hooks ([9feec85](https://github.com/kouroshez/coding-os/commit/9feec85cfe365fc6b405e893d47ddc7ecb30763e))
* **adapters:** pass a real UUID as the SDK session id — new CLI rejects non-UUID --session-id ([186bd35](https://github.com/kouroshez/coding-os/commit/186bd35a8e5ff82cdc907ee9d4db34e928f5aace))
* **board_os:** panel-first session attribution to stop cross-panel drift ([a30804c](https://github.com/kouroshez/coding-os/commit/a30804ca930f9404d945661dd60a9368e1535b60))
* **board:** board-churn auto-commit fires on 'local' autonomy + Hub lists local_autonomous ([b51fc31](https://github.com/kouroshez/coding-os/commit/b51fc31c186f57e037fa366b6c62d103c44b1bd3))
* **board:** flag icebox zombie cards + bilingual task-mode classifier ([867198d](https://github.com/kouroshez/coding-os/commit/867198d8cfb91828faa2ce866a0d9df0274eff27))
* **board:** merge duplicate frontmatter blocks in 12 task files that sync rejected ([d5384e7](https://github.com/kouroshez/coding-os/commit/d5384e7472b2112888a3c70f1242c1231f88340a))
* **board:** prune deleted-file task rows on full sync, cascade to child tables ([baa05aa](https://github.com/kouroshez/coding-os/commit/baa05aa8e835acd5c936481139e5779594f36a72))
* **board:** stop phantom NULL-reason reverts from idle sibling panels ([53f7941](https://github.com/kouroshez/coding-os/commit/53f79419239cf0be4216e080e91bf53723f6cd8c))
* **board:** YAML-quote frontmatter list items, map legacy fallback status to icebox+ready ([0cf3eac](https://github.com/kouroshez/coding-os/commit/0cf3eace29a5c38e87173986db830011fd1eeda5))
* **ci:** exclude .ruff_cache from manifest + golden capture — dev-cache pollution ([7f7ec5a](https://github.com/kouroshez/coding-os/commit/7f7ec5aa293144905c30d6ff972ddb1514c566b8))
* **ci:** resolve 7 Linux-only full-sweep failures + unblock fresh uv resolution ([3edb38e](https://github.com/kouroshez/coding-os/commit/3edb38eb4ceba391854df58993400ccb5d78f69a))
* **ci:** resolve adapter-scoped hooks in registry test + drop herestring read-loop ([0bd5989](https://github.com/kouroshez/coding-os/commit/0bd5989dce746c0f018a95667cf3f8af76fd5d52))
* **cli:** apply ultra-review findings to generated CI/Dockerfiles + stack-lint ([0bdfac6](https://github.com/kouroshez/coding-os/commit/0bdfac64b5dc0a97758faca833bda4b5bd19a784))
* **cli:** cos init substitutes placeholders in all text files, not a 7-extension allowlist ([6cfc5c9](https://github.com/kouroshez/coding-os/commit/6cfc5c9201673a486c47b1800ce62f8eaf95d5cc))
* **cli:** create each adapter's root entrypoint symlink during init and update ([beceeaa](https://github.com/kouroshez/coding-os/commit/beceeaa691786b6726a15bd1fe125583eb92e8ce))
* **cli:** detect nested same-language root collisions + longest-pattern boundary owner ([f451639](https://github.com/kouroshez/coding-os/commit/f4516395033b7d64fa5c10889a441d642997c2a8))
* **cli:** drop shadowed graph-reindex dup, wire cos-mcp-start entry, portable trace-replay path ([e5e292f](https://github.com/kouroshez/coding-os/commit/e5e292f1b1c237bebc122052ecdd1ebc9b8af054))
* **cli:** ensure_gitignore tops up runtime carve-outs on an existing .gitignore ([7683191](https://github.com/kouroshez/coding-os/commit/76831913abe713f78070b787e90249a0d838b151))
* **cli:** honest post-init next steps + document the Hub-optional CLI loop ([df11cdf](https://github.com/kouroshez/coding-os/commit/df11cdfdbbe6db3a29d64e6ffdef1facb7aacfff))
* **cli:** honor adapter_scope in doctor hook.coverage check ([a5f220d](https://github.com/kouroshez/coding-os/commit/a5f220df843953a782b82357237ab93639c88e03))
* **cli:** post-init quick start prints commands that actually run ([0a3ce3f](https://github.com/kouroshez/coding-os/commit/0a3ce3f29107074016824512082f4326f70fd82f))
* **cli:** renderer preserves file mode; node-express Node&gt;=21; astro doc drift ([b37476b](https://github.com/kouroshez/coding-os/commit/b37476b36ea8f7fbcc8e8425025ea33adfcb678a))
* **cli:** stream init progress to stderr in json mode so create phases advance ([1ba7395](https://github.com/kouroshez/coding-os/commit/1ba7395c8991dcbfaf546f048c6050df6dbdc0ca))
* **codex:** preserve runtime identity across Hub and hooks ([0607bd0](https://github.com/kouroshez/coding-os/commit/0607bd06501e2c036d45b71dccaecea374399f20))
* **codex:** wire warn-diff-size into codex pretool dispatch + kernel module ([8f2345a](https://github.com/kouroshez/coding-os/commit/8f2345a7229a9cf9be259f504bace03b05d1cdd6))
* **cognition:** drop repairer's spurious canonical_order; align onboarder registry pin ([8d93307](https://github.com/kouroshez/coding-os/commit/8d93307363f0485ef12925bf60f34a9d5e725438))
* **core:** anatomy lessons require a recorded remedy; harvest skips headers and frontmatter ([572e6a0](https://github.com/kouroshez/coding-os/commit/572e6a054e6ca6c5175bd1c1bd65d4b22afda6de))
* **core:** attribute unattended board maintenance to a system actor, not the human operator ([9e9fa18](https://github.com/kouroshez/coding-os/commit/9e9fa180172e14b9cdb73ccf033cd193da403c51))
* **core:** cos_search recall correctness — read-only, semantic filters, FTS5 escaping ([8faa9b6](https://github.com/kouroshez/coding-os/commit/8faa9b6e45a37e6e4270ec0fe0d89637a2cc5995))
* **core:** drop hardcoded claude-opus-4-8 literals that broke the anthropic guard suite ([912199c](https://github.com/kouroshez/coding-os/commit/912199ce45a7fb2fb648425fa85899f8dfd683bd))
* **core:** full graph stub list, project-root doc-header guard, drop dead experiment script ([fba8c8b](https://github.com/kouroshez/coding-os/commit/fba8c8b9c563f087aeb7ece607cfefe484513549))
* **core:** gate parallel dispatch on projected cost so an N-way fan-out cannot overrun the cap ([a021a6d](https://github.com/kouroshez/coding-os/commit/a021a6d0ada694a2ab3c2ad58940a5e5c66155e5))
* **core:** honor bound project scope over $COS_DB_PATH in resolve_db_path ([316dbdb](https://github.com/kouroshez/coding-os/commit/316dbdbddf814a8175d31c3f5a95e816f5ab0957))
* **core:** let the distiller use the adapter turn default; filter tool-fumble noise from lessons ([79f2dff](https://github.com/kouroshez/coding-os/commit/79f2dff904380cc1ff2114aab3d1e5026c884838))
* **core:** memory lifecycle safety — fresh breakthrough survival + trust_tier decay guard ([2f3c45c](https://github.com/kouroshez/coding-os/commit/2f3c45c91152bf9479735f1e3e1bfac738d07496))
* **core:** missing DB rows no longer block the nightly board-drift auto-commit ([257ee2c](https://github.com/kouroshez/coding-os/commit/257ee2cb9a640a0bb26a19713438f75bcbe3b1bc))
* **core:** outcomes/metrics loop — dedup outcome_history + add time_to_solution metric ([90be61c](https://github.com/kouroshez/coding-os/commit/90be61caff8ccc57d035e30d0d21ca0b4bb28fff))
* **core:** own 3 delta hooks + fix profile assertion; add tool-owner guard + module verify-suite ([cf723b8](https://github.com/kouroshez/coding-os/commit/cf723b826e79d679db27d22f1e1ccdfc5eb78d49))
* **core:** panel-scoped gate resolution in session_enrich ([2b9cea9](https://github.com/kouroshez/coding-os/commit/2b9cea91cc4eabf16dfddf207b4c9fd73e966793))
* **core:** raise board-drift commit timeout to 600s for large staged sets ([46d89b6](https://github.com/kouroshez/coding-os/commit/46d89b6cb113e67002fcf245ce973e8593537098))
* **core:** refuse $HOME as a project root so no phantom DB is minted in the hub state dir ([dc90611](https://github.com/kouroshez/coding-os/commit/dc90611817c3170f70206bfb049772df072d1d44))
* **docs-lint:** audit the last unwatched doc subtree + GitHub-accurate anchor slugs ([fb29bfd](https://github.com/kouroshez/coding-os/commit/fb29bfdc71ec69ee1c0e65c331fbcf1533531e9e))
* **error-sweep:** classify hook BLOCKs as policy via log_events.event_class ([57880c0](https://github.com/kouroshez/coding-os/commit/57880c0d4f6a35017f865c257ce6d36e3a210a0b))
* **fastapi:** async-first sample endpoint + test, declare pytest-asyncio ([88cf676](https://github.com/kouroshez/coding-os/commit/88cf676d5cb7a678aa7b8fb4aa46edf38f1802cd))
* **graph:** declare networkx as base dep so the Communities view populates ([0953961](https://github.com/kouroshez/coding-os/commit/095396133d86cb785b6b45037f51ba92f0f8a81c))
* **graph:** map live extractor ids to provenance, cover edges in export cache signature ([ea50272](https://github.com/kouroshez/coding-os/commit/ea50272359f16c0c1570b2ef98fac5202c41adde))
* **graph:** sweep folder-spine + phantom residue on full graph-reindex reconcile ([7b0d0cc](https://github.com/kouroshez/coding-os/commit/7b0d0cc98098e5c13669ca5009d81397df8927c6))
* **graph:** type-only TS imports emit imports_type, not a runtime cycle edge ([3044b94](https://github.com/kouroshez/coding-os/commit/3044b949e58a9c31d118d34979675f4056aeee16))
* **hooks:** block-protected-files guards src/core skills+rules source, not just renders ([be70b1f](https://github.com/kouroshez/coding-os/commit/be70b1f9b44b7949a36aafa79dcc974c20f50140))
* **hooks:** close git long-option-abbreviation bypasses in 3 client-side guards ([c3fc906](https://github.com/kouroshez/coding-os/commit/c3fc90663137151688ffb3265d96b75dae33fdfa))
* **hooks:** defer heredoc/command-substitution commit -m values instead of mis-validating them ([3da488a](https://github.com/kouroshez/coding-os/commit/3da488a15f3074ff24cab34cfe6997f10899350e))
* **hooks:** drop dead TodoWrite matcher from track-discovery, clarify Work-Log-vs-todo policy ([672aaba](https://github.com/kouroshez/coding-os/commit/672aabaf57c68910e4b6c40fa3a952be54ac5c6a))
* **hooks:** re-arm abandoned-task warning on task-state-change ([cdb210c](https://github.com/kouroshez/coding-os/commit/cdb210cc84dbce5d989f7580adb2978e13d8ca9c))
* **hooks:** test-governor lock uses owner-agent pid + release leg, not host-global pgrep ([784d320](https://github.com/kouroshez/coding-os/commit/784d3207b180d05e1e82f834bdab2849898001a7))
* **hub-ui:** read producer response shapes, send CSRF on mutations, re-scope live logs ([438d960](https://github.com/kouroshez/coding-os/commit/438d96018dbfa41174877bdc49dee0e17f117792))
* **hub-ui:** update vulnerable transitives + react-router-dom to the patched 7.18 ([8a07454](https://github.com/kouroshez/coding-os/commit/8a074541518f0d0872ef6ff93ec7d6046b0c989f))
* **hub:** a11y sweep — WAI-ARIA tablists/listbox + keyboard-operable rows/cards (TASK-835) ([bfe5689](https://github.com/kouroshez/coding-os/commit/bfe5689d5c39ec979abc6a26b2d9e88df835df79))
* **hub:** align Observability/CommandPalette/trace consumers to producer field names ([d18bea1](https://github.com/kouroshez/coding-os/commit/d18bea178e7f38125d86be70d64b45f0ed8d95bf))
* **hub:** allow config mutations on coding-os; mark only active skills on; kernel badge nowrap ([7af2b5b](https://github.com/kouroshez/coding-os/commit/7af2b5bb7262524b537a30481dc9e0bac1d821be))
* **hub:** bound trace replay, presence allow-list, patterns envelope (TASK-833) ([64415b2](https://github.com/kouroshez/coding-os/commit/64415b2aed688a49908854b37f7dcf06b5dd6c61))
* **hub:** close module sets over dependents and let the onboarding marker expire ([49234af](https://github.com/kouroshez/coding-os/commit/49234af42d8cb99e912c52440ce09fa1012b77d0))
* **hub:** correct SupportFooter repo handle (kouroshez) + drop 404 payment placeholders (TASK-836) ([160d092](https://github.com/kouroshez/coding-os/commit/160d0922451ee07b68da09f4728becec70062bfb))
* **hub:** data-drive RolesPage agent picker + render single-integer model ids ([ef28ae3](https://github.com/kouroshez/coding-os/commit/ef28ae3fcb98202c1aa3cdea20903a783a0a685e))
* **hub:** harden /api/sessions payload + bound search sys.path & graph export (TASK-833) ([a1e2b89](https://github.com/kouroshez/coding-os/commit/a1e2b898027a0e27f0af0efe12955cf79c39cab3))
* **hub:** honest telemetry + working Activity bell + Search redesign ([e10719f](https://github.com/kouroshez/coding-os/commit/e10719f91ca3f8b9306df5f9f09c1b2333bad93c))
* **hub:** honor per-request project scope over ambient env in Hub routes ([591c75e](https://github.com/kouroshez/coding-os/commit/591c75e385d134a001ecebf6faf5fe4c8788cf9c))
* **hub:** isolate scheduled run-now, honor cron hour, scope client logs (TASK-834) ([ce00714](https://github.com/kouroshez/coding-os/commit/ce00714c6c1483dfcbf31370b38601ce969ab382))
* **hub:** keep board toolbar and zoom controls clear of the stream/legend/tweaks panels ([c6d295b](https://github.com/kouroshez/coding-os/commit/c6d295bcd5c5b921d7a208c2ffb961592896a10d))
* **hub:** keyboard-operable switch toggles + WAI-ARIA tablist nav (TASK-835) ([1735f00](https://github.com/kouroshez/coding-os/commit/1735f00d3e2090413a6a6b81e0b3f4429a9ad902))
* **hub:** make Composer module chips authoritative and land users in the new project ([be52b9d](https://github.com/kouroshez/coding-os/commit/be52b9da5e3ae2c8019b94a672d2d75d33f9dec7))
* **hub:** make HealthAlarmBar link scope-aware and reconnect LiveStatus SSE on project switch ([3b286e6](https://github.com/kouroshez/coding-os/commit/3b286e6d042c71ec4d56e99db7524653cdccc60c))
* **hub:** plain-language module refusal string + surface toggle cascade notes ([a359ab1](https://github.com/kouroshez/coding-os/commit/a359ab1e9cd0af7f93d522955d966ac45ca074d1))
* **hub:** preserve task Work Log on board edit; focus deep-linked task; trim dead bell events ([df89c7d](https://github.com/kouroshez/coding-os/commit/df89c7d6d46ffd829233492441636aca7fba64ea))
* **hub:** re-open the Composer when a create job is still running after a reload ([82d59cc](https://github.com/kouroshez/coding-os/commit/82d59cc8ff9a13f7f05c3574e6db89a2d96da7c7))
* **hub:** real per-session ctx badges for every adapter ([2f90be9](https://github.com/kouroshez/coding-os/commit/2f90be920074049b166dc3a57665d210a93f90b3))
* **hub:** review fixes for config mutations — cos JSON parse, argv guard, cwd shadow ([fd6f686](https://github.com/kouroshez/coding-os/commit/fd6f686d7d7c5e1052851350eb629e80848ed023))
* **hub:** stop the board "+ more" button re-fetching an exhausted column page ([6e99330](https://github.com/kouroshez/coding-os/commit/6e993304186252ad2b3faa63b846f542a8d19542))
* **hub:** surface fetch failures on Diagnostics Overview and the Roles panel ([5bd29d1](https://github.com/kouroshez/coding-os/commit/5bd29d10e36b7f36dcd85ad6c327b319b90ee040))
* **learning:** emit enum-valid domain header on filed narratives ([7f8da3c](https://github.com/kouroshez/coding-os/commit/7f8da3c1fa956ec0b8b68474758f0a07ed8cc547))
* **learning:** link filed narratives to the real slugged task file ([e6dbadd](https://github.com/kouroshez/coding-os/commit/e6dbadd6e118876f4880b98a75c4fe81eb66c083))
* **learning:** mine anatomy lessons from remedy-less backtracks via canonical remedies ([cebc260](https://github.com/kouroshez/coding-os/commit/cebc26030b288db24baaf3624254216b98a6803f))
* load Codex transcripts in Hub chat ([fa4176e](https://github.com/kouroshez/coding-os/commit/fa4176eb60351c5cc7ce0587e4b19f0278045677))
* **memory:** drain embedding-outbox under rag interpreter + BGE-M3 similarity floor ([303530f](https://github.com/kouroshez/coding-os/commit/303530f3703de1d64d0a78440df438f57f0a5117))
* **memory:** hide mechanical capture rows as changelog + session-wide write-dedup ([8d8479e](https://github.com/kouroshez/coding-os/commit/8d8479e2d9a9403796857853d3cea2382e2c542d))
* **memory:** recalibrate BGE-M3 memory floor 0.55-&gt;0.45 to restore synonym recall ([9ef1c44](https://github.com/kouroshez/coding-os/commit/9ef1c446d7ec60dd02db2061655676d661b2a7a7))
* **memory:** relabel MEMORY.md trusted-lessons badge validated→seen ([a8a4891](https://github.com/kouroshez/coding-os/commit/a8a48916236119259bfc58a90fb650ac7d0f7173))
* **memory:** split conflated times_validated into times_seen vs times_validated (v49) ([8bdaafd](https://github.com/kouroshez/coding-os/commit/8bdaafda05c24530ccbf0818df79fc94299b6c9a))
* **nightly:** reconcile orphan doc chunks + run memory_gc; column-guard gc ([2e105ac](https://github.com/kouroshez/coding-os/commit/2e105ac66ad9e861409b1f80d0486619d25c620d))
* **node-express:** exclude test files from pre-install tsc typecheck ([8eef5b7](https://github.com/kouroshez/coding-os/commit/8eef5b700db76846857c25eb3dbe9c453cabcc6a))
* **onboarding:** keep readiness on one signal and stop json mode emitting prose ([284bd0f](https://github.com/kouroshez/coding-os/commit/284bd0f4ed28cf38b272e2fbb7df827fd1a2d8b8))
* **pr:** distinguish merge-queue queued/ejected from pending in ci rollup ([5804f16](https://github.com/kouroshez/coding-os/commit/5804f16bdd027980834afaf9bd942a4eab1b7ccf))
* **pr:** harden owner-stamp liveness — refresh on re-open, parse pid past a quoted host ([3dcc75c](https://github.com/kouroshez/coding-os/commit/3dcc75cfe6c24ff93f984ea721478b63378c13b7))
* **pr:** reaper skips a live-but-presence-less worktree via the lock-owner pid ([99bf24c](https://github.com/kouroshez/coding-os/commit/99bf24c3ff560d413eed50598b6918a8899c8eef))
* **pr:** surface review-required so auto_merge does not silently deadlock on reviews ([91a5acf](https://github.com/kouroshez/coding-os/commit/91a5acf231bb88cd262fed5d40fd59c0d6e62d32))
* **readme:** color-safe release badge URL so release-please version bumps keep the color ([5af523f](https://github.com/kouroshez/coding-os/commit/5af523f820f666e1eb2d9420d7ce29e59165982a))
* **readme:** dynamic GitHub release badge — works now the repo is public ([e3333b5](https://github.com/kouroshez/coding-os/commit/e3333b5ca54322f1440ff7c14da5f56bc174c011))
* regenerate derived artifacts left stale by the codex-parity change ([4980d93](https://github.com/kouroshez/coding-os/commit/4980d93a5ebc6af813e782e9b89c519a1672176c))
* **release:** self-updating README release badge via release-please extra-files ([83aeef2](https://github.com/kouroshez/coding-os/commit/83aeef2cb25cb70f8b44da0a12d49b4ac3ba1688))
* **review:** apply code-review findings from the 9-task backlog (bugs + doc-drift) ([7a31d0e](https://github.com/kouroshez/coding-os/commit/7a31d0ebe60232d3157f78727d0ebfcab89bd00a))
* **review:** apply ultra-code-review findings to the TASK-633..642 backlog ([ae99d3f](https://github.com/kouroshez/coding-os/commit/ae99d3f91e2d26b4570462c8f463035327b63d0c))
* **review:** correct 6 bugs introduced by the code-review fix batch ([00f5821](https://github.com/kouroshez/coding-os/commit/00f582114455bd9559131356172b79dad2197f39))
* **review:** RED test + test-modules coverage + regex/UI guards from max-effort review ([18a1a40](https://github.com/kouroshez/coding-os/commit/18a1a40d0997e6a6404ac93f436084b79d48bfbc))
* **review:** relocate $HOME DB guard to init_db; board sends full body to keep Work Log ([437a83c](https://github.com/kouroshez/coding-os/commit/437a83cce02f3964d03c82077037a8992887dd8a))
* **review:** restore resolve_db_path raise as the complete $HOME guard; swap fresh Work Log on edit ([789fa67](https://github.com/kouroshez/coding-os/commit/789fa6770bb6c88162116ff26e690f2448594194))
* **scheduled:** nightly.py runs as a direct script — bootstrap src + src/core on sys.path ([3e9d133](https://github.com/kouroshez/coding-os/commit/3e9d133bd1fa65144ca22507a924547269e21508))
* **security:** declare and enforce why credential-shaped test fixtures are safe ([3ee0980](https://github.com/kouroshez/coding-os/commit/3ee0980a74e95b0f34526d1c55992e6635c76089))
* **templates:** astro problem.ts emits the canonical error envelope, not RFC 9457 ([af67293](https://github.com/kouroshez/coding-os/commit/af6729344102a6c3c3b57a073275dc82661cf53e))
* **templates:** astro sample test passes astro check; pin Node&gt;=20 for global crypto ([7eec749](https://github.com/kouroshez/coding-os/commit/7eec749bb102ad4b7a8576b06ade49e87db44547))
* **templates:** complete go-fiber v3 migration across docs, skill, rules, boundary ([3fed8b4](https://github.com/kouroshez/coding-os/commit/3fed8b4dfd43a81fb35a07c29d638a497a627f6e))
* **templates:** conform nestjs error filter and docs to the error-format.md envelope ([d867b31](https://github.com/kouroshez/coding-os/commit/d867b314bad879ead553dfa6390a53d30963fd3f))
* **templates:** gate every task-system instruction in AGENTS.md fragments on modules.tasks ([934ffab](https://github.com/kouroshez/coding-os/commit/934ffab5022cc1954763e1457bc80899ea9335d0))
* **templates:** honest verify + day-one sample tests for 5 stacks ([3032b3f](https://github.com/kouroshez/coding-os/commit/3032b3fbf9fafe0c732ded1b2605d2bd84cbb96f))
* **templates:** nestjs 11, laravel 12 and puma 7.2.1 floors clear their advisories ([7973138](https://github.com/kouroshez/coding-os/commit/79731384f784649f892493ad21a7eb0a7251f680))
* **templates:** node-express verify command drops the dead npx-eslint prefix ([ece4d48](https://github.com/kouroshez/coding-os/commit/ece4d48a54836e9c2e85be857adeebe34750378e))
* **templates:** npm floors above known-vulnerable ranges + repair the SvelteKit toolchain ([a056afd](https://github.com/kouroshez/coding-os/commit/a056afd67381f097ec11a6b893910368be22c7bc))
* **templates:** quote the go.mod module placeholder so Go can parse it ([b9556c5](https://github.com/kouroshez/coding-os/commit/b9556c5944dea005a687fd852e559c8c30b69bb9))
* **templates:** raise the go-fiber dependency floors past 21 advisories ([1a30a05](https://github.com/kouroshez/coding-os/commit/1a30a0583a001b60f5c440e86500c5ca92b4cf6e))
* **templates:** relocate wordpress skill to its stack overlay (stop over-shipping) ([5aaecf1](https://github.com/kouroshez/coding-os/commit/5aaecf15da3d74f64a1c779fbd6cb1a6bb8d963e))
* **templates:** remove go/go-fiber/svelte shipped-artifact drift ([b56e7f0](https://github.com/kouroshez/coding-os/commit/b56e7f021c2032c4ca601b44e7a071dda8df1f87))
* **templates:** repair 4 shipped hard-breaks (dangling rules, go-fiber v3, mvnw, astro content-seo) ([5491a31](https://github.com/kouroshez/coding-os/commit/5491a31e2cd9c6005ed3eedc15a525369197e796))
* **templates:** ship angular accessibility doc for the playbook's a11y link ([6c6d4b5](https://github.com/kouroshez/coding-os/commit/6c6d4b5f913a8fe63bd179dfd5023a451f88cdd5))
* **templates:** ship aspnet-core xUnit test project for green dotnet test on init ([00b5e3e](https://github.com/kouroshez/coding-os/commit/00b5e3ed24c7d8c027a19201a867ce0345389289))
* **templates:** ship go-fiber go.sum so go vet/test pass on a fresh init ([14fa174](https://github.com/kouroshez/coding-os/commit/14fa1742cd5b521085b4b6ed889b8adef3b52bf1))
* **templates:** spring-boot scaffold google-java-format + bind spotless to verify ([5c37c61](https://github.com/kouroshez/coding-os/commit/5c37c61457dd67607872141cda22d65762319eef))
* **templates:** svelte vite.config import + vue-nuxt vitest/vite major skew ([769022e](https://github.com/kouroshez/coding-os/commit/769022e55b7039d415f6ca56ce27fb66ae9ece63))
* **templates:** sync nextjs/wordpress verify substitutions + revert day-one-red changes ([60d33cb](https://github.com/kouroshez/coding-os/commit/60d33cb7e97dabc893c9d52b53feac70c2a00d09))
* **templates:** wire cross-adapter Channel-2 memory-read pointer into AGENTS.md ([03b6272](https://github.com/kouroshez/coding-os/commit/03b6272ca9744aab52dbec8f04d006cc37dabc81))
* **test:** -S in nightly smoke test so the editable finder can't mask a broken bootstrap ([d472dd3](https://github.com/kouroshez/coding-os/commit/d472dd3d4f3bb3559691913f4e4a45703a2fc76a))
* **thinking_os:** atomic observation dedup via partial UNIQUE index (migration v51) ([ba19476](https://github.com/kouroshez/coding-os/commit/ba19476e3ab833831b48735cab6ea1f3c08057ec))
* **thinking_os:** close the learn-validate loop on the MCP completion path ([3596628](https://github.com/kouroshez/coding-os/commit/35966287bbfb60cb21bbc6c5066548e8a1498109))
* **thinking_os:** session_summary bootstraps src/ so it runs as a file ([13fbc5f](https://github.com/kouroshez/coding-os/commit/13fbc5fdfd8f151dfe1dfde0e1e6d2d38a6d6921))
* **web:** attribute unowned panel move/reposition to the human actor ([72a5a51](https://github.com/kouroshez/coding-os/commit/72a5a514c7f8473d57bdee671d63919c9c10af40))


### Performance

* **core:** guard jit-nudge mkdir behind a dir-exists check ([3132974](https://github.com/kouroshez/coding-os/commit/31329745dced7d05a828f3e96954f6fab75a463f))
* **pr:** reaper sweep lists worktrees once (O(N)) and rejects foreign-host owners ([6da9fa9](https://github.com/kouroshez/coding-os/commit/6da9fa93685d0506e1189fbf771ba82d4470be64))
* **tests:** class-scoped scaffold for TestInit + TestClaudeAdapter (cos-init once per class) ([270bfd5](https://github.com/kouroshez/coding-os/commit/270bfd54de1b4943a0df458baba2a94fb1372285))


### Changed

* **board:** self-documenting names over comments in board_coherence ([e4b5bb4](https://github.com/kouroshez/coding-os/commit/e4b5bb45128a18343bd98e9591bb5f39cedaa092))
* **core:** compress git-workflow, test-discipline, transparency-banner rules 42 percent ([c7b7e56](https://github.com/kouroshez/coding-os/commit/c7b7e563c787348e15bfd24e381e73bfec01d42b))
* **core:** disjoin graph_query/graph_search + honest kernel always-on tool floor ([e21c904](https://github.com/kouroshez/coding-os/commit/e21c9049c988fb40e362939b6e154361a4e2f60a))
* **core:** drop dead completion_gap read-paths + cos_learn_feedback; measured [Memory] pulse ([eb1cd88](https://github.com/kouroshez/coding-os/commit/eb1cd886fbeefd50132ad885b4164f59b7486467))
* **golden:** single SECTIONS SSOT module for capture + parity test ([4676343](https://github.com/kouroshez/coding-os/commit/4676343fbbea9cc312751cab76a56a388e98b361))
* **hooks:** behavior-parity harness + delete transitional warn-template-drift hook ([b649219](https://github.com/kouroshez/coding-os/commit/b649219027e2dc19431d9d436db9d26658157454))
* **hub:** decompose ChatView (806L) into chat-turns + chat-turn-views (TASK-836) ([ddbeda6](https://github.com/kouroshez/coding-os/commit/ddbeda6cfffaf3678724cbe46ebe0d38a1931e28))
* **hub:** decompose ConfigPage (1855L) into features/config modules (TASK-836) ([29d1da3](https://github.com/kouroshez/coding-os/commit/29d1da3f91735965b789388a6451bb363793498b))
* **hub:** derive the scheduled-endpoint payload types from the OpenAPI schema ([4d20b19](https://github.com/kouroshez/coding-os/commit/4d20b198ed7ee72472cb6809b80701fde1339134))
* **hub:** extract board modals/badges/panels from CosBoardPage (TASK-836) ([079cd98](https://github.com/kouroshez/coding-os/commit/079cd987ce65270d5ee684b9e98e6369699ace61))
* **hub:** extract board-shared (types/constants/helpers/context) from CosBoardPage (TASK-836) ([fb5cf9b](https://github.com/kouroshez/coding-os/commit/fb5cf9b0229a3e9ab85f5208f26fb08214bd0e6f))
* **hub:** extract git-tab-data (types/presets/tips) from GitTab (TASK-836) ([571ae20](https://github.com/kouroshez/coding-os/commit/571ae20a68f9943e37c0f7f58d51c843bd74c56f))
* **hub:** extract TaskDetailDrawer + history into task-detail from CosBoardPage (TASK-836) ([c278e5b](https://github.com/kouroshez/coding-os/commit/c278e5b36e95c870beb6baca3ca66f6dcb8f698a))
* **hub:** extract TaskStickyCard/SwimlaneLabel + TopBar from CosBoardPage (TASK-836) ([6cdb7f2](https://github.com/kouroshez/coding-os/commit/6cdb7f26f510484862a3cafc95d2f378038b6b92))
* **hub:** extract the stream-event and trace-timeline models from their views ([637929d](https://github.com/kouroshez/coding-os/commit/637929d4a78f046ba5418ad2f674b3e01b738994))
* **hub:** route MemoryPage/DoctorPage through api-client (TASK-836) ([aef6a75](https://github.com/kouroshez/coding-os/commit/aef6a7576986f6c26947b6d472c384438c7b9866))
* **hub:** split board-modals into 4 modules all &lt;400 (TASK-836) ([66db651](https://github.com/kouroshez/coding-os/commit/66db6519a2243698cbd763a41b1e607181690a2d))
* **hub:** split board-panels into 4 panel modules all &lt;400 (TASK-836) ([4a29f1f](https://github.com/kouroshez/coding-os/commit/4a29f1f8ddad36ce08be671ad7511f2688439d66))
* **hub:** split CosBoardPage into data/view/dnd hooks + grid — main 928-&gt;233 ([0aec11c](https://github.com/kouroshez/coding-os/commit/0aec11c26c11d20e339dfe6e721f3ceb89e99e76))
* **hub:** split task-detail drawer + GitTab so every module is under 400 lines ([e02c38e](https://github.com/kouroshez/coding-os/commit/e02c38e81716f614cc397fa3ce49d52eff2d8a1d))
* **hub:** split task-detail into drawer + history + edit-form (TASK-836) ([d14ae4e](https://github.com/kouroshez/coding-os/commit/d14ae4ef67ee24c1c49994e6c8739dbfdd7dfa23))
* **thinking_os:** drop dead record_review + auto-record memory-check on cos_search ([1c9f6a3](https://github.com/kouroshez/coding-os/commit/1c9f6a38617293155a843cd75c7058526ee20fbd))


### Documentation

* **adapters:** define current Codex capability and SDK contract ([550ec27](https://github.com/kouroshez/coding-os/commit/550ec273af2e95dbfea2a9f2c85e153b358e6b82))
* **adapters:** state the enforced P8 boundary and sanctioned lazy-import carve-out ([ad52c18](https://github.com/kouroshez/coding-os/commit/ad52c18cf0ac4ff0c1a4687cccb7c6ba5a2a8dfc))
* **adr:** kernel scope boundaries (ADR-0015) + dispatch-deferral partially revived ([2eedc43](https://github.com/kouroshez/coding-os/commit/2eedc432e9582ffaa675ca136956da6ab1f66f75))
* align public-facing docs with current reality before first release ([c1be9cc](https://github.com/kouroshez/coding-os/commit/c1be9cc06b3ef53fbf169938fa1004544f30b21c))
* **api:** regenerate openapi.json — spec drifted from live routes ([5c114dd](https://github.com/kouroshez/coding-os/commit/5c114dd831b633b812075a8ffbc61119b9ebe44f))
* **architecture:** complete raptor lens — density, operational cost, worked case study ([e2622cd](https://github.com/kouroshez/coding-os/commit/e2622cd35303076ed74a3ef1b6155cb40a320814))
* **core:** align dispatcher contract with current Codex runtimes ([2ba7dd4](https://github.com/kouroshez/coding-os/commit/2ba7dd4cf32a48d49be15051b5c9bd57f6fb8742))
* drop residual references to removed third-party material ([70788bb](https://github.com/kouroshez/coding-os/commit/70788bb9ab2244167a8cd6d3d249dc1924665d70))
* **engineering:** July 2026 modularity re-audit + variability-completion backlog ([3bdec6c](https://github.com/kouroshez/coding-os/commit/3bdec6c430ae0cec2e996029918e00c1f24b1ba3))
* **engineering:** register derived-store coherence audit in the index ([a66d7aa](https://github.com/kouroshez/coding-os/commit/a66d7aa940de3473a9c805522f373970b1aff3c7))
* fix onboarding clone URLs and stale governance references ([b7606ed](https://github.com/kouroshez/coding-os/commit/b7606ede060a8d3572354a53844571116d72986c))
* **governance:** add Critical Rule 26 — verify by executing, not by reading ([fc753f7](https://github.com/kouroshez/coding-os/commit/fc753f75a51d50392f6b9f368e5ba41d3a533373))
* **governance:** add product vision + raptor consolidation lens as SSOT docs ([09f98f8](https://github.com/kouroshez/coding-os/commit/09f98f86e6ad39b5a26dc56ee00672de25ffb28e))
* **hub:** tick-by-tick pre-release audit report for the Hub UI ([66a9032](https://github.com/kouroshez/coding-os/commit/66a903244054c1698704e3bdb8dfac433585a33f))
* **index:** commit stale auto-index regen for adapters + engineering ([c988f74](https://github.com/kouroshez/coding-os/commit/c988f748b443c205cfe6370fa89f89e87abaf1fe))
* **index:** list pr-mode-ci-economics playbook in the auto-index (TASK-619) ([30240e9](https://github.com/kouroshez/coding-os/commit/30240e9c316f005d5e98b694b3ba62ef29272c2a))
* **index:** re-sort engineering index for the modularity-audit updated date ([5f7e783](https://github.com/kouroshez/coding-os/commit/5f7e783126c2f2cbfd431d21e0c0ab242f5008ad))
* lead with the modular story — take only what you need ([d2166e9](https://github.com/kouroshez/coding-os/commit/d2166e99b95d51264841e3c28a58c9ddbba2edb8))
* Maven Wrapper attribution per Apache-2.0 4(d) + final name sweep ([63780e1](https://github.com/kouroshez/coding-os/commit/63780e15f80d44cbe73419475d83b12567796fa3))
* **memory:** mark QW-3 shipped as detector, not column (SSOT) ([9d3eb02](https://github.com/kouroshez/coding-os/commit/9d3eb025461bf36e06dafedb056c10d37f1d61b8))
* **memory:** persist icebox-parking structural-failure finding ([8ff6772](https://github.com/kouroshez/coding-os/commit/8ff67720d5d08a8044babceac0b7b0517b909548))
* **memory:** reconcile memory.md + retro.md with the shipped memory/metrics tools ([2035405](https://github.com/kouroshez/coding-os/commit/20354050714202bab3d71ea7f12112089f296dfa))
* **modularity:** record pass-7 audit + inline the tasks-&gt;docs rationale ([28af4da](https://github.com/kouroshez/coding-os/commit/28af4da9806fa5cfaa7ff07c950ad1369c431bc7))
* **onboarding:** document the panel-first install path and the module/profile axis ([0be8570](https://github.com/kouroshez/coding-os/commit/0be8570301ff9d518bb6c8a27c08f1425d78a097))
* **pr:** pr-mode CI economics — fast-gate/full-suite split + reference workflow ([c49adc0](https://github.com/kouroshez/coding-os/commit/c49adc05c4ed7ebccf0aa6642feaebf66485ce80))
* **readme:** accurate profile ladder + paste-safe shell fences ([3b9da11](https://github.com/kouroshez/coding-os/commit/3b9da11af0acd130e58f47d9ed5fe6b431e7a568))
* **readme:** drop the per-project token figures from the scoping section ([2ab0420](https://github.com/kouroshez/coding-os/commit/2ab0420521bda92521d7371ae285af1e2a067e17))
* **readme:** dynamic release badge so the version never goes stale ([26dca36](https://github.com/kouroshez/coding-os/commit/26dca3636e29709f3c2e9cc1f2658afa041e0059))
* **readme:** lead with measured context economics + a visible support surface ([e265f88](https://github.com/kouroshez/coding-os/commit/e265f88ea365d213b1927a34e480c44a0640abaa))
* **readme:** live CI workflow badge now that Actions run green in public ([f5046da](https://github.com/kouroshez/coding-os/commit/f5046dacb69866739fd033b1525e28927ddf573f))
* **readme:** point the version badge at PyPI instead of GitHub releases ([f7376f3](https://github.com/kouroshez/coding-os/commit/f7376f3c1c91681207a87bf4faeb523a96c32458))
* **readme:** restore Sponsor links now that GitHub Sponsors is live ([c297ed3](https://github.com/kouroshez/coding-os/commit/c297ed3085327c60ed232830565ebf776155ceb8))
* **readme:** slim the front page — move graph/docker deep-dives to engineering docs ([f57f446](https://github.com/kouroshez/coding-os/commit/f57f44668308447972c4201f5af769f74d320f66))
* **readme:** state skill scoping accurately with measured numbers ([57f2cd0](https://github.com/kouroshez/coding-os/commit/57f2cd01f62b444fe7eb3bebbfe9b4d87ab886f0))
* replace absolute developer paths with neutral placeholders ([5b2b723](https://github.com/kouroshez/coding-os/commit/5b2b723f3aad426d52ff1fe989a63749b52ccd88))
* research multi-adapter supervisor architecture ([339450c](https://github.com/kouroshez/coding-os/commit/339450cf52f8bcd1cb749e8b465761ddc9e0d7c9))
* **rules:** add Test cadence policy to test-discipline.md ([e53417f](https://github.com/kouroshez/coding-os/commit/e53417f655eb812fb04abb2b8f078cc4c248c3a3))
* Smoke row in testing-strategy + the as-file bootstrap invariant in scheduled-jobs and hook-authoring. Regenerated golden (hook + skill drift). ([fa33a84](https://github.com/kouroshez/coding-os/commit/fa33a849e9b98c09943c5f9f113a977a9c85039e))
* **templates:** add references/anatomy.md to 13 bare stack skills ([631b4eb](https://github.com/kouroshez/coding-os/commit/631b4ebcc4b2df82f95880404b6ff50794fabd46))
* **test:** refresh stale suite-size figures to ~4,850/327 files ([0b4e41f](https://github.com/kouroshez/coding-os/commit/0b4e41fb899504aaa97a8daea5168badbbe1f830))
* **tests:** testmon spike verdict — DEFER (redundant with verify-ledger dedup) ([b02515d](https://github.com/kouroshez/coding-os/commit/b02515d0ae08e9ee6545a18a903958e181ec1623))
* translate all remaining non-English prose to English ([f26ff1d](https://github.com/kouroshez/coding-os/commit/f26ff1d0861e830b634518cd9e640e40a541bdc4))
* **workflow:** ship the modularity note to consumer projects, not just the meta-repo ([e213025](https://github.com/kouroshez/coding-os/commit/e213025416ceba859c26d49b0861ac56adbd4591))


### Build

* pin ruff==0.15.15 — floating pin broke the CI format gate on each release ([d72421e](https://github.com/kouroshez/coding-os/commit/d72421e951595335d6b6f147aef701b6fcd3e7fa))
* **release:** pin last-release-sha so the changelog starts at 0.3.4 ([e09bc04](https://github.com/kouroshez/coding-os/commit/e09bc041ba9ad95945611aa3b20273cd92d63c2d))

## [0.3.4](https://github.com/kouroshez/coding-os/compare/v0.3.3...v0.3.4) (2026-08-05)


### Fixed

* **docs-lint:** audit the last unwatched doc subtree + GitHub-accurate anchor slugs ([02c8a5b](https://github.com/kouroshez/coding-os/commit/02c8a5bed5db35d118df8f2bf1d89f67f4e8ff22))
* **hub-ui:** update vulnerable transitives + react-router-dom to the patched 7.18 ([f4a942d](https://github.com/kouroshez/coding-os/commit/f4a942d1e21f3e357b8cdd24312c7ea44a52dee5))
* **security:** declare and enforce why credential-shaped test fixtures are safe ([bad64a7](https://github.com/kouroshez/coding-os/commit/bad64a76717d3a099391342dc8d52211303e0b60))
* **templates:** nestjs 11, laravel 12 and puma 7.2.1 floors clear their advisories ([1a602ec](https://github.com/kouroshez/coding-os/commit/1a602ec7a05cec143d90e3350de388afb93058d9))
* **templates:** npm floors above known-vulnerable ranges + repair the SvelteKit toolchain ([5143d3a](https://github.com/kouroshez/coding-os/commit/5143d3aee14eec181603f2d6996c1e8cf0237a92))
* **templates:** quote the go.mod module placeholder so Go can parse it ([3254a44](https://github.com/kouroshez/coding-os/commit/3254a44dab4d03766e3a1d1409be3aa874cb199d))

## [0.3.3](https://github.com/kouroshez/coding-os/compare/v0.3.2...v0.3.3) (2026-08-04)


### Fixed

* **cli:** honest post-init next steps + document the Hub-optional CLI loop ([cf434fa](https://github.com/kouroshez/coding-os/commit/cf434fab4b4df3126336fbe112c1e6b71019b5f8))
* **cli:** post-init quick start prints commands that actually run ([729ce10](https://github.com/kouroshez/coding-os/commit/729ce10d16f3e70c11c0804ac35adfeac6fd94b1))
* **readme:** color-safe release badge URL so release-please version bumps keep the color ([4ff70b4](https://github.com/kouroshez/coding-os/commit/4ff70b4a2b98c625615b064093a2fac5a260287b))
* **readme:** dynamic GitHub release badge — works now the repo is public ([70a4699](https://github.com/kouroshez/coding-os/commit/70a469911860ba4a2d6c9257c857433c5724402d))


### Documentation

* lead with the modular story — take only what you need ([50e4bb6](https://github.com/kouroshez/coding-os/commit/50e4bb693b1241fb0d81b66e14e7300da3c92ea4))
* Maven Wrapper attribution per Apache-2.0 4(d) + final name sweep ([6068c3e](https://github.com/kouroshez/coding-os/commit/6068c3e7fe327aed8249209b0dc5a33cea70ccda))
* **readme:** accurate profile ladder + paste-safe shell fences ([ce1ba81](https://github.com/kouroshez/coding-os/commit/ce1ba8152ce6331a02ca7f4644dcfbe468b7d683))
* **readme:** live CI workflow badge now that Actions run green in public ([488531c](https://github.com/kouroshez/coding-os/commit/488531cd681c2fdaefeb6d19a104eda4b27b6279))
* **workflow:** ship the modularity note to consumer projects, not just the meta-repo ([467776a](https://github.com/kouroshez/coding-os/commit/467776ab62d39ea64b8a4518048e3424acbc089d))

## [0.3.2](https://github.com/kouroshez/coding-os/compare/v0.3.1...v0.3.2) (2026-08-04)


### Added

* **docs-lint:** audit all root *.md and resolve link targets case-exactly ([a441719](https://github.com/kouroshez/coding-os/commit/a4417196baf172e46d1e5a79385ae55775100b99))


### Fixed

* regenerate derived artifacts left stale by the codex-parity change ([3068588](https://github.com/kouroshez/coding-os/commit/306858831cf170a40550fb2baef7e2ba0ad212ab))
* **release:** self-updating README release badge via release-please extra-files ([a11c909](https://github.com/kouroshez/coding-os/commit/a11c909603856c7807b91260affeeed9e50f42ba))


### Documentation

* **readme:** dynamic release badge so the version never goes stale ([3a35cf5](https://github.com/kouroshez/coding-os/commit/3a35cf5f837990e661012e242eca38d774b4e940))
* **readme:** restore Sponsor links now that GitHub Sponsors is live ([1eba56d](https://github.com/kouroshez/coding-os/commit/1eba56dd80b191b049142338f82a030e05c936f8))
* **readme:** slim the front page — move graph/docker deep-dives to engineering docs ([5a792da](https://github.com/kouroshez/coding-os/commit/5a792dad7b3199d2927c400177ae146f3fbd5837))
* replace absolute developer paths with neutral placeholders ([e0ff839](https://github.com/kouroshez/coding-os/commit/e0ff839b8c1a36603c766764976309136ddc9ec1))

## [0.3.1](https://github.com/kouroshez/coding-os/compare/v0.3.0...v0.3.1) (2026-08-04)


### Added

* **adapters:** complete Codex SDK and hook parity ([c0e1870](https://github.com/kouroshez/coding-os/commit/c0e187054b2a905c985d378805f7d2ba7058fc5d))
* **adapters:** dual Claude auth mode — subscription OAuth or API key, selectable in Hub panel ([7743797](https://github.com/kouroshez/coding-os/commit/77437972339703d7bff9ce0fe569460aab5c8ee1))
* **adapters:** refresh Codex SDK and hook parity ([2abec02](https://github.com/kouroshez/coding-os/commit/2abec02ad3a5c5218aa05b26a44fe20abdb76ff6))
* **adapters:** versioned agent memory — in-repo .agents/memory with self-repairing harness symlink ([099fef0](https://github.com/kouroshez/coding-os/commit/099fef0f62e44cb4e5b2f390070747c65dbb8f70))
* **board:** autonomy-gated auto-commit of board↔git drift + fix silent drift-task filing ([93de359](https://github.com/kouroshez/coding-os/commit/93de359f586341695d511c642e6358ec91188fb8))
* **board:** blocked-lane SLA aging via blocked_sla_hours knob (observability only) ([fc8c5d1](https://github.com/kouroshez/coding-os/commit/fc8c5d1ad25b73bf882bbe92aacfc3c7504e934d))
* **board:** graduated DoD acceptance gate at complete + fix for_kind merge clobber ([ae11594](https://github.com/kouroshez/coding-os/commit/ae11594de35349509e8d5ea0311e61ef79c8cb4e))
* **board:** hook-block trend KPI in cos retro (blocks/session vs prior period) ([46ce11b](https://github.com/kouroshez/coding-os/commit/46ce11bf668702dbe262a3f4e6c3749910dfafc5))
* **board:** warn on session-created un-ready icebox cards (create-then-park nudge) ([74c684e](https://github.com/kouroshez/coding-os/commit/74c684ef44d5b6bd0fd8cb9190748da34c99b577))
* **cli:** --enable-module escape from profile+disable union on init/adopt ([92e22e3](https://github.com/kouroshez/coding-os/commit/92e22e3fca34bbd570b26c2b8ff71014e96f035c))
* **cli:** add owner-gated brain-sweep-changelog to retire legacy changelog rows ([2746981](https://github.com/kouroshez/coding-os/commit/274698117e5abdf6c2f3c8f654f58d9f9da22ff3))
* **cli:** generate backend Dockerfiles at init — render_dockerfile, cicd-gated ([3417a51](https://github.com/kouroshez/coding-os/commit/3417a51c72c4c40181b150be919a00f00e7918ca))
* **cli:** generate consumer CI workflow at init — render_ci_workflow, cicd-gated ([d5519e2](https://github.com/kouroshez/coding-os/commit/d5519e24228d9d047144900fe6d81965df52a5a5))
* **cli:** mention --preset in the interactive stack prompt ([54c69df](https://github.com/kouroshez/coding-os/commit/54c69dff764bb6e24776bb16539c7bd1dc040d6d))
* **cli:** stack-lint v2 soft checks + factory rows 13-18 + 4 backfilled rules ([a67c9b1](https://github.com/kouroshez/coding-os/commit/a67c9b185eb3f3c184cce310899178fea411ac9b))
* **cognition:** persist sub-agent transcript + cos cognition log --transcript ([1cb24c6](https://github.com/kouroshez/coding-os/commit/1cb24c62a3b1d01a9bb0feef747a0005e6c2b097))
* **core:** doctor rule_drift + doc_drift audit + Hub drift banner (F-D) ([f4bee05](https://github.com/kouroshez/coding-os/commit/f4bee055f4204112bc7c970f0d76c3959ad279cd))
* **core:** JIT convention-rule reminders via jit-recall glob map (jit-rules.tsv) ([a15378b](https://github.com/kouroshez/coding-os/commit/a15378bb6ba47d65b623f2526a7931a5b0702c70))
* **core:** live agent pip on task cards — pulse while the bound session works, click opens its chat ([dd05259](https://github.com/kouroshez/coding-os/commit/dd052592dad08b43bb3df51546eb0fd943783f4f))
* **core:** live-toggle doc prune/restore + correct doc_drift source mapping (F-B) ([eb89852](https://github.com/kouroshez/coding-os/commit/eb898528a29c0d26e8ad1e3cc2aedb3792d27caf))
* **core:** LLM friction-lesson distiller behind the dispatcher port (idempotent, budget-capped) ([0b70e65](https://github.com/kouroshez/coding-os/commit/0b70e65393d7b314562c63cb9d3b8c7263f0d40b))
* **core:** module-owned rules — cascade-unlink a disabled module's rules (F-A) ([af56209](https://github.com/kouroshez/coding-os/commit/af56209fc19eacdae46eec64b9f639a20ead1ab7))
* **core:** out-of-core module overlay so a plugin registers a module without forking (F-F) ([91d4ea0](https://github.com/kouroshez/coding-os/commit/91d4ea0fa3daa38148af680ed3721bc108be372c))
* **core:** promotion ladder — promoted lessons leave belief surfaces; retro drafts rule promotions ([cd79983](https://github.com/kouroshez/coding-os/commit/cd79983bfc509ca63086023861e4bbbbb3f8ad40))
* **core:** settings-gated board auto-spawn — drag icebox-&gt;in_progress dispatches an implementer ([17b282b](https://github.com/kouroshez/coding-os/commit/17b282b05d5afa9751ce33cec8c1de6d2854b9e9))
* **cost:** dispatch cost analytics + budget ladder; fix budget spent-today query ([2b539e7](https://github.com/kouroshez/coding-os/commit/2b539e7481f9d00a49588945008c98d5840cbe3f))
* **dispatch:** cost-routed multi-model dispatch — bandit, cheaper reviewer, adapter hint ([83ead02](https://github.com/kouroshez/coding-os/commit/83ead02d9d031968e8491f8b264db587709a1808))
* **dispatch:** per-chain budget ceiling, EvidenceBundle flock, max_turns hop-cap ([c4fa7ff](https://github.com/kouroshez/coding-os/commit/c4fa7ffd701bee1602f0709c3515adc2e11a319c))
* **docs:** lint scaffold docs for untagged module-owned slash commands (F-H) ([1554365](https://github.com/kouroshez/coding-os/commit/15543657cf409f1027e7aabdfd46f4eecba36779))
* **governor:** dedup make-target verify suites, not only bare pytest ([0d56c79](https://github.com/kouroshez/coding-os/commit/0d56c79ff68fd13abe1b94be46e97b130083333c))
* **hooks:** nudge-git-mode + banner git=pr field so pr-mode is surfaced proactively ([dab639b](https://github.com/kouroshez/coding-os/commit/dab639bd14a48db4b99f18afdcb93c87e2bf2aaa))
* **hooks:** nudge-reentry UserPromptSubmit reminder for an unbound in_progress task ([94eb7b2](https://github.com/kouroshez/coding-os/commit/94eb7b2d610a03d9cbc8905ceb73449915e75646))
* **hooks:** session-end advises on uncommitted non-docs code at end-of-turn ([b53ba48](https://github.com/kouroshez/coding-os/commit/b53ba48321b9a5fdfcdff10fa1823319fdaf527d))
* **hooks:** visible hook-parity deficits (N1) + rename-completeness teeth (N11) ([951817f](https://github.com/kouroshez/coding-os/commit/951817f3a174769d8a758b29a6ded691d4d9a93f))
* **hooks:** warn-diff-size nudges diff-minimal commits (fail-open) ([7ec570c](https://github.com/kouroshez/coding-os/commit/7ec570c5b6613c27790a7083077d97cb05063692))
* **hub:** add Config Adapters tab with runtime, models, and MCP wiring ([14997c4](https://github.com/kouroshez/coding-os/commit/14997c4179854eb095d3db17b43991f591877a87))
* **hub:** add Marketplace top-nav tab (Extension Manager coming-soon) ([b77abef](https://github.com/kouroshez/coding-os/commit/b77abef0c738de258e83b5e75931fce413815dd3))
* **hub:** config stack/adapter/MCP install-remove endpoints (meta-guarded) ([636e416](https://github.com/kouroshez/coding-os/commit/636e4167acfb115ef114ad264ab7c3c5236931db))
* **hub:** consolidate IA — Settings into Config, Memory into Workspace, slim Diagnostics ([0c6e665](https://github.com/kouroshez/coding-os/commit/0c6e66563685f2ea1d3da8f2b3ff8871a4b8292b))
* **hub:** declutter task HISTORY — commits-first default, details behind a toggle ([d2bf41b](https://github.com/kouroshez/coding-os/commit/d2bf41b2bc1b05b5a0856b2f99d53d676286925e))
* **hub:** live dispatch observability via trace tee, SSE tail route, and chat fallback ([82f308f](https://github.com/kouroshez/coding-os/commit/82f308fd5e73b2180492d3d176d46d3f1743fc8c))
* **hub:** mark installed adapters in /api/config/adapters ([c098bf8](https://github.com/kouroshez/coding-os/commit/c098bf80efed5ca257dcca176a8a8c48f1a561ee))
* **hub:** Memory tab — validation-rate headline, tier groups, lesson evidence ([341e3ee](https://github.com/kouroshez/coding-os/commit/341e3eee3ca136385d427a053c2334be11eea78e))
* **hub:** ModulesTab discloses commands/rules + inline refusal reason + dependency why (F-E) ([8bd5757](https://github.com/kouroshez/coding-os/commit/8bd5757b931f53d60dd5525e9a0df1150ea4248c))
* **hub:** move Overview into Workspace and restore the Design tab ([d7f0414](https://github.com/kouroshez/coding-os/commit/d7f041431be5c9f0c380b1fb9c7cfc788de3d4d5))
* **hub:** redesign Config tabs — installed-first stacks, grouped skills, adapter/MCP add-remove ([0c4c0fc](https://github.com/kouroshez/coding-os/commit/0c4c0fc92f829b0f8a821ef9e1211cc3f2ebda6b))
* **hub:** SettingsPage single-save flow — bottom Save flushes scheduled edits (TASK-836) ([4b1c46d](https://github.com/kouroshez/coding-os/commit/4b1c46d2c75e10bc6ac6df46daaf6b1159fb62ed))
* **hub:** show module reverse-deps + skills; pre-empt a blocked disable in Config ([ab35f7e](https://github.com/kouroshez/coding-os/commit/ab35f7e54798c340ecaa6f5b0f3ffc4133cfe6a6))
* **hub:** tag presets with provenance and clarify the composer preset choice ([4fb5ad5](https://github.com/kouroshez/coding-os/commit/4fb5ad5dd230a76907bb5c4b3f12c247e53183f6))
* **hub:** typecheck every SPA API path against the generated OpenAPI types ([84f82ea](https://github.com/kouroshez/coding-os/commit/84f82ea70177b78dd9e6b9f5618cc3a5fd3d3026))
* **learning:** derive per-task reward label from the verify ledger (v52) ([833fba5](https://github.com/kouroshez/coding-os/commit/833fba501922692d4583dd906839c3416d915809))
* **learning:** fire the validation loop for formal tasks + honest trust deflation ([300a8fd](https://github.com/kouroshez/coding-os/commit/300a8fdc3e882f31a1df032058ddd9b8c50239f4))
* **memory:** async per-session LLM enrichment of changelog observations (default-OFF) ([c63c52c](https://github.com/kouroshez/coding-os/commit/c63c52c0501db3dd44db3f14594ac38de0999ae9))
* **memory:** fidelity-gated session_summaries.learned via apply_session_facts ([a759a73](https://github.com/kouroshez/coding-os/commit/a759a73d0e35335f3fd989440967e79b045e9e50))
* **memory:** MMR diversity + column-weighted FTS5 + RRF fusion in cos_search ([7f2b484](https://github.com/kouroshez/coding-os/commit/7f2b484847f75c7cf1af9a8ad59e213cf393980b))
* **memory:** wire expires_at forward — TTL stamp at capture + decay GC of expired rows ([6198221](https://github.com/kouroshez/coding-os/commit/61982216a02f64a5f5341c41021f036e0bee52fc))
* **modules:** lite install profile + per-module hint discovery in Hub ([4f9815d](https://github.com/kouroshez/coding-os/commit/4f9815d37939382b3d723eafbdc4dab8ad396cff))
* **pr-mode:** cos pr conflicts — early-warning file overlap across agent branches ([3564a23](https://github.com/kouroshez/coding-os/commit/3564a23b0c66d4d24e4bf3c133802072d7f959ac))
* **pr:** bootstrap worktree gitignored deps + secrets so first validate works ([a2635f4](https://github.com/kouroshez/coding-os/commit/a2635f46ecfd4c74f99501f499d4f659178e4f2d))
* **pr:** cos pr triage — ranked digest of open agent PRs for the review bottleneck ([9ae239c](https://github.com/kouroshez/coding-os/commit/9ae239c3dbce28c6867c8ccc1028b797f0052b68))
* **pr:** local_autonomous rung — cos pr land merges to local integration, guard-carved ([d6cb2dc](https://github.com/kouroshez/coding-os/commit/d6cb2dc27ee2740cf4e23ecac2dfeb3d88fb19f4))
* **pr:** warn on unprotected integration branch + mark local-rung merge human-only ([fdcc42c](https://github.com/kouroshez/coding-os/commit/fdcc42c40e1664a347f84a1b4fddbfc38a25b6c8))
* **pulse:** surface last verify-suite result in the agent pulse ([63c17a8](https://github.com/kouroshez/coding-os/commit/63c17a8b950252f4eb0db2d94c7502c4af71b476))
* **repair:** budget-capped autonomous repair loop + dispatchable repairer ([84a4ef8](https://github.com/kouroshez/coding-os/commit/84a4ef88f6eecb8c6836781fec506897d5c009b3))
* **routing:** flag-gated Thompson-sampling Beta-Bernoulli model router ([05ce062](https://github.com/kouroshez/coding-os/commit/05ce0623b3d5ff2e3e330946c29c6ce253fb2fa0))
* **stack-lint:** flag a shipped sample test that verify never runs ([dbc8be0](https://github.com/kouroshez/coding-os/commit/dbc8be0448f99318d39880e6d06e5fb06ff82990))
* **templates:** add famous-stack presets mern, nuxt-fullstack, laravel-vue, go-react ([37355b0](https://github.com/kouroshez/coding-os/commit/37355b00fd9dc33cccafc13fe645532f4e2fd9a1))
* **templates:** bootable fastapi + django scaffolds (manifest, entrypoint, test, verify) ([c829604](https://github.com/kouroshez/coding-os/commit/c82960494b077a3c01a49c0bef79817e552d4f69))
* **templates:** bootable go + go-fiber scaffolds (go.mod, cmd/api entrypoint, test, verify) ([29d33d4](https://github.com/kouroshez/coding-os/commit/29d33d40a628a15e0eaa1330aabb077801772c2b))
* **templates:** bootable nextjs + react-native seeds + flat ESLint migration ([1ac6921](https://github.com/kouroshez/coding-os/commit/1ac692172ce701acb4c42d39efa520993043da61))
* **templates:** bootable wordpress php seed (composer.json + phpcs PSR-12) ([48fcbd2](https://github.com/kouroshez/coding-os/commit/48fcbd291954099631a93c699c570f4aa403ab60))
* **templates:** bump astro scaffold to v7 with the Content Layer API ([bc243bf](https://github.com/kouroshez/coding-os/commit/bc243bf5143c717c734ce39cac5f2fa9da106638))
* **templates:** language config bundle for go/rust/ruby/php/dart linters ([ac0d35a](https://github.com/kouroshez/coding-os/commit/ac0d35ad3784287d0a0a008a6b5fef1546de9681))
* **templates:** migrate angular scaffold to v22 with Vitest unit-test runner ([0d52c15](https://github.com/kouroshez/coding-os/commit/0d52c15203140d33a751c0cc2df996e680265271))
* **templates:** per-language toolchain config bundle selected by stack language ([52bc7a7](https://github.com/kouroshez/coding-os/commit/52bc7a70a190388d00cc5b95d03a2fee57d38395))
* **templates:** seed .editorconfig + base .gitignore in _base/scaffold ([bab7893](https://github.com/kouroshez/coding-os/commit/bab7893a465bb134933e2f5e20b9819151fd0bfd))
* **verify:** add test-web-ui (vitest) suite + make ui-test target ([49e8221](https://github.com/kouroshez/coding-os/commit/49e82216fb20b4ad4724e97e29e88693357d1032))


### Fixed

* **adapters:** add Sonnet 5 / Fable 5 to Claude model catalogue, bump SDK to 0.2.110 ([12608aa](https://github.com/kouroshez/coding-os/commit/12608aa0a6e011d4b97d5ee0fa2e09eed061781d))
* **adapters:** drop codex delegates pointing at removed core hooks ([5c544ae](https://github.com/kouroshez/coding-os/commit/5c544ae9d3e23bf06236ad7b99ee0fe9905d2156))
* **adapters:** pass a real UUID as the SDK session id — new CLI rejects non-UUID --session-id ([4aad3dd](https://github.com/kouroshez/coding-os/commit/4aad3dd6f511187203048c0f21a72ec9039a9564))
* **board_os:** panel-first session attribution to stop cross-panel drift ([6b48e05](https://github.com/kouroshez/coding-os/commit/6b48e05de36f24f419ea36b48101d090d93b070f))
* **board:** board-churn auto-commit fires on 'local' autonomy + Hub lists local_autonomous ([4496d3e](https://github.com/kouroshez/coding-os/commit/4496d3e6fa1887f28278be56d96ac7b8bfaae2f1))
* **board:** flag icebox zombie cards + bilingual task-mode classifier ([10634d2](https://github.com/kouroshez/coding-os/commit/10634d2dff69037c46c383549475b2e3c893aad7))
* **board:** merge duplicate frontmatter blocks in 12 task files that sync rejected ([235af22](https://github.com/kouroshez/coding-os/commit/235af229017957c48de82f9da9128af91afff8db))
* **board:** prune deleted-file task rows on full sync, cascade to child tables ([f9a709d](https://github.com/kouroshez/coding-os/commit/f9a709dd81f78ee717d7c2c321642b383168e65c))
* **board:** stop phantom NULL-reason reverts from idle sibling panels ([36932e0](https://github.com/kouroshez/coding-os/commit/36932e0328fdb9f5b9150ea74df97bd8e1245b97))
* **board:** YAML-quote frontmatter list items, map legacy fallback status to icebox+ready ([f59840c](https://github.com/kouroshez/coding-os/commit/f59840cf9a73008175bfd12ba5c3ef39a1d4c904))
* **ci:** exclude .ruff_cache from manifest + golden capture — dev-cache pollution ([85979f7](https://github.com/kouroshez/coding-os/commit/85979f7914fb640d2081774f7fad4a540c9f549e))
* **ci:** resolve 7 Linux-only full-sweep failures + unblock fresh uv resolution ([d51c753](https://github.com/kouroshez/coding-os/commit/d51c753d35b0e54be39dbc31746479b02abd1364))
* **ci:** resolve adapter-scoped hooks in registry test + drop herestring read-loop ([416148f](https://github.com/kouroshez/coding-os/commit/416148fec19167f334818046d57997c0d1937aac))
* clarify git config safety limits ([ed2d582](https://github.com/kouroshez/coding-os/commit/ed2d582f921b4cc37783440dd72b69c2bdfb1f26))
* **cli:** apply ultra-review findings to generated CI/Dockerfiles + stack-lint ([d206735](https://github.com/kouroshez/coding-os/commit/d206735eb74469daa1bcb2472430575ecc2d94ef))
* **cli:** cos init substitutes placeholders in all text files, not a 7-extension allowlist ([f1fe393](https://github.com/kouroshez/coding-os/commit/f1fe3930db05495b61e5777934eab3a43a8044b4))
* **cli:** detect nested same-language root collisions + longest-pattern boundary owner ([2716ce6](https://github.com/kouroshez/coding-os/commit/2716ce68230a9f55d3aecf8b7a22fdd78f9f7434))
* **cli:** drop shadowed graph-reindex dup, wire cos-mcp-start entry, portable trace-replay path ([8b7326b](https://github.com/kouroshez/coding-os/commit/8b7326bb1f3c11f854981977c9562be1daf22a9d))
* **cli:** ensure_gitignore tops up runtime carve-outs on an existing .gitignore ([59a5fe9](https://github.com/kouroshez/coding-os/commit/59a5fe9c9e87ae87ccaffa38e17a452e549393c9))
* **cli:** honor adapter_scope in doctor hook.coverage check ([5b7b2cc](https://github.com/kouroshez/coding-os/commit/5b7b2cc14ee3917afdefd011c2f8caf72f904538))
* **cli:** materialize wires Makefile -include only when a stack contributes targets ([2235b83](https://github.com/kouroshez/coding-os/commit/2235b835ce2f1c3ad2edbeb39462c502589bed5e))
* **cli:** renderer preserves file mode; node-express Node&gt;=21; astro doc drift ([81d5434](https://github.com/kouroshez/coding-os/commit/81d5434bf63ad67cf6d895234ad5feb1ac2b9446))
* **cli:** stream init progress to stderr in json mode so create phases advance ([04ff999](https://github.com/kouroshez/coding-os/commit/04ff99927ed50d8d825fc594a833b5738023b4d7))
* **codex:** preserve runtime identity across Hub and hooks ([12a8bb6](https://github.com/kouroshez/coding-os/commit/12a8bb6590bdfdf013f0c77757cacf6e0bcc3fe5))
* **codex:** wire warn-diff-size into codex pretool dispatch + kernel module ([0d1319c](https://github.com/kouroshez/coding-os/commit/0d1319c3f541ca3ced890fd648ae422a63b8b30c))
* **cognition:** drop repairer's spurious canonical_order; align onboarder registry pin ([f6c1b1b](https://github.com/kouroshez/coding-os/commit/f6c1b1bbf36ef3cbbddfdb376cccaff891c4900c))
* **core:** anatomy lessons require a recorded remedy; harvest skips headers and frontmatter ([023b91f](https://github.com/kouroshez/coding-os/commit/023b91fa23b5a53bad9156b712656273e0e0829e))
* **core:** attribute unattended board maintenance to a system actor, not the human operator ([aa88cb4](https://github.com/kouroshez/coding-os/commit/aa88cb41e143700f9c3033bc7ca27a17088074ce))
* **core:** cos_search recall correctness — read-only, semantic filters, FTS5 escaping ([435bc5a](https://github.com/kouroshez/coding-os/commit/435bc5a7d0476ad2fe4d81f4eb8d2db3aab0efd2))
* **core:** drop hardcoded claude-opus-4-8 literals that broke the anthropic guard suite ([0ba07f2](https://github.com/kouroshez/coding-os/commit/0ba07f272ed652311bd7a5ddb32b5a0bec8e47ea))
* **core:** full graph stub list, project-root doc-header guard, drop dead experiment script ([a5a2111](https://github.com/kouroshez/coding-os/commit/a5a2111eeed7bfe38fb4260e511d8d7d7dae5aa5))
* **core:** gate parallel dispatch on projected cost so an N-way fan-out cannot overrun the cap ([15b0d12](https://github.com/kouroshez/coding-os/commit/15b0d122ffb18f1430d2893487585718e7e3f99f))
* **core:** honor bound project scope over $COS_DB_PATH in resolve_db_path ([16b863f](https://github.com/kouroshez/coding-os/commit/16b863f3fecd9d340815fae263cb6b3cd7643cf6))
* **core:** let the distiller use the adapter turn default; filter tool-fumble noise from lessons ([7caf198](https://github.com/kouroshez/coding-os/commit/7caf19878b641cc6a40b353de193b51970ceb168))
* **core:** memory lifecycle safety — fresh breakthrough survival + trust_tier decay guard ([7fca22b](https://github.com/kouroshez/coding-os/commit/7fca22b738cc6bd35cb6956377e5737e1c1114c6))
* **core:** missing DB rows no longer block the nightly board-drift auto-commit ([de8fb34](https://github.com/kouroshez/coding-os/commit/de8fb34bde9d2b911870d60c013b8a1d50f8831a))
* **core:** outcomes/metrics loop — dedup outcome_history + add time_to_solution metric ([3f657b3](https://github.com/kouroshez/coding-os/commit/3f657b3794756c9ac602eac2e851da8ea90090c9))
* **core:** own 3 delta hooks + fix profile assertion; add tool-owner guard + module verify-suite ([ef5d46f](https://github.com/kouroshez/coding-os/commit/ef5d46f2d5a7ea4f2958dcadfa4b0eff76c2a196))
* **core:** panel-scoped gate resolution in session_enrich ([a3170da](https://github.com/kouroshez/coding-os/commit/a3170daecd8c370b30a0e60213498e236cb743c4))
* **core:** raise board-drift commit timeout to 600s for large staged sets ([f0f65a3](https://github.com/kouroshez/coding-os/commit/f0f65a3e320506dd160da658aee4cbac0803ddcc))
* **core:** refuse $HOME as a project root so no phantom DB is minted in the hub state dir ([b6ca44a](https://github.com/kouroshez/coding-os/commit/b6ca44af8719f7561f178c331b43ffc39967ceca))
* detect unmanaged hub listeners ([e8e157e](https://github.com/kouroshez/coding-os/commit/e8e157e3f551615c6ee32c2ff5c6c3ee08ff5535))
* enforce protected branch patterns ([ee3a85f](https://github.com/kouroshez/coding-os/commit/ee3a85f6238e4c5238ed899a4be1a3c80ff6543f))
* **error-sweep:** classify hook BLOCKs as policy via log_events.event_class ([d944209](https://github.com/kouroshez/coding-os/commit/d944209578e389b4c39142dd876fca9e86633fdc))
* **fastapi:** async-first sample endpoint + test, declare pytest-asyncio ([4a1ddb1](https://github.com/kouroshez/coding-os/commit/4a1ddb1576c62ef836569a6c132bf1451bf5ec11))
* **governance:** put comment-provenance ban in always-on Rule 12 + de-contradict TODO hook ([7971e51](https://github.com/kouroshez/coding-os/commit/7971e51a502e73f508dba8f558967e698c693b23))
* **graph:** declare networkx as base dep so the Communities view populates ([34b5e9a](https://github.com/kouroshez/coding-os/commit/34b5e9a2688095b3bff1676e96d796337673c340))
* **graph:** honest references count, impact visit_limit + freshness, dead_code FP (cluster 3) ([742d9ef](https://github.com/kouroshez/coding-os/commit/742d9efbc3d8542759ccac663737a3665eed84a0))
* **graph:** map live extractor ids to provenance, cover edges in export cache signature ([ae5b34b](https://github.com/kouroshez/coding-os/commit/ae5b34b07e7c1539d0c131278244dcde185ce691))
* **graph:** MCP-written freshness-bound graph-gate markers (cluster 1) ([8f32678](https://github.com/kouroshez/coding-os/commit/8f32678691602826764f456eae686c17ceb615ce))
* **graph:** sweep folder-spine + phantom residue on full graph-reindex reconcile ([badce59](https://github.com/kouroshez/coding-os/commit/badce59a0d6d0a6f4c5ec609359dfe20ca113dcc))
* **graph:** type-only TS imports emit imports_type, not a runtime cycle edge ([fa38916](https://github.com/kouroshez/coding-os/commit/fa3891645ddce9f2fedfbb14257a8bff990de907))
* **hooks:** block-protected-files guards src/core skills+rules source, not just renders ([142c321](https://github.com/kouroshez/coding-os/commit/142c32179236ab71fa63c8e17c77dfc405197a93))
* **hooks:** block-secrets blocks all git-hook-skip bypasses (-n, path/cd/env, core.hooksPath) ([894709d](https://github.com/kouroshez/coding-os/commit/894709d1c5d4145108440e5fd3b754f32812802d))
* **hooks:** branch-guard trunk blocks force-rewrite of main + update-ref (pr-mode parity) ([c329c5e](https://github.com/kouroshez/coding-os/commit/c329c5e6e58da60595160bde77feb2d11b41db5f))
* **hooks:** close 6 code-review bypasses/FPs in branch-guard + block-secrets + pr-cleanup (TASK-565) ([ed21433](https://github.com/kouroshez/coding-os/commit/ed2143397fa8787d7ccba769af48141520bcb375))
* **hooks:** close git long-option-abbreviation bypasses in 3 client-side guards ([f0934a7](https://github.com/kouroshez/coding-os/commit/f0934a7a0d177d1d79c8866405d3c97107d018b5))
* **hooks:** close git-safety bypasses F1-F5 via shared shlex tokenizer ([b0792a5](https://github.com/kouroshez/coding-os/commit/b0792a5bc0cb6f9a78ffee1ab53e890fae9a7276))
* **hooks:** close indirection, settings-write & pr-mode update-ref HEAD git-guard bypasses ([236f8ce](https://github.com/kouroshez/coding-os/commit/236f8ce912187947ac4c3b2fb81ccfbe9c1578fb))
* **hooks:** close separator/grouping bypass of git-verify gate + order-independent force-push ([2679f5b](https://github.com/kouroshez/coding-os/commit/2679f5b045e6314e78d62fbab5c2037489277924))
* **hooks:** context-budget marker no longer reports stale pre-compact ctx after /compact ([cf20bcc](https://github.com/kouroshez/coding-os/commit/cf20bccecf291dd155fa1d7c0a911f8240623484))
* **hooks:** context-budget marker no longer reports stale pre-compact ctx after /compact ([1022a4a](https://github.com/kouroshez/coding-os/commit/1022a4abe2d8edd6a7eaf4f244671502db1fce60))
* **hooks:** data-driven graph-explorer gate in enforce-skill (cluster 2) ([50bca95](https://github.com/kouroshez/coding-os/commit/50bca959de44beb8625b1a2f60fac845d4b0e12f))
* **hooks:** defer heredoc/command-substitution commit -m values instead of mis-validating them ([7c573f1](https://github.com/kouroshez/coding-os/commit/7c573f13456ef613bb4984169d46d96097cc8a96))
* **hooks:** drop dead TodoWrite matcher from track-discovery, clarify Work-Log-vs-todo policy ([e9b70b7](https://github.com/kouroshez/coding-os/commit/e9b70b7f64fb9fdb6a36efb10891879a41878ccb))
* **hooks:** re-arm abandoned-task warning on task-state-change ([50f41d5](https://github.com/kouroshez/coding-os/commit/50f41d50ad892f5a97f088ca054dd4adc49be762))
* **hooks:** surface git_settings fail-open downgrades + jq↔python parity test ([49be78a](https://github.com/kouroshez/coding-os/commit/49be78abf6ce13bd70daae18e5cae801247c38dc))
* **hooks:** surface state-misroute in the per-turn banner ([8704d8f](https://github.com/kouroshez/coding-os/commit/8704d8f8a6a620e414bb791042c3ef02096dd8fe))
* **hooks:** test-governor lock uses owner-agent pid + release leg, not host-global pgrep ([a41227f](https://github.com/kouroshez/coding-os/commit/a41227fe2954d15c23166e609127ee541831938f))
* **hub-ui:** confirm pr-mode enable + meta hard-block, always-probe, agent-only note ([08c658a](https://github.com/kouroshez/coding-os/commit/08c658a2668333551a22804986acd42a1f6dd2ad))
* **hub-ui:** read producer response shapes, send CSRF on mutations, re-scope live logs ([25cc454](https://github.com/kouroshez/coding-os/commit/25cc4548006c575920568a6b34e9d25899e9af33))
* **hub:** a11y sweep — WAI-ARIA tablists/listbox + keyboard-operable rows/cards (TASK-835) ([6212163](https://github.com/kouroshez/coding-os/commit/6212163329407b48e5fbb7943846645ac70de6ae))
* **hub:** align Observability/CommandPalette/trace consumers to producer field names ([3bae64f](https://github.com/kouroshez/coding-os/commit/3bae64f7ecef2988841e7d8593ed37def8f7fe05))
* **hub:** allow config mutations on coding-os; mark only active skills on; kernel badge nowrap ([b973437](https://github.com/kouroshez/coding-os/commit/b9734377b529d017ad0cb2bf6332185174c5ffb9))
* **hub:** bound trace replay, presence allow-list, patterns envelope (TASK-833) ([0ce795d](https://github.com/kouroshez/coding-os/commit/0ce795da41a9aabc31c763043e1d37b442f2c031))
* **hub:** close module sets over dependents and let the onboarding marker expire ([b7df636](https://github.com/kouroshez/coding-os/commit/b7df636905f097678909dfbbc5ffacc4b3b297a1))
* **hub:** Config→Git highlights the active preset, not the Recommended badge ([1709204](https://github.com/kouroshez/coding-os/commit/170920414b4a30ba3a158e6451282859f4d59a28))
* **hub:** correct SupportFooter repo handle (kouroshez) + drop 404 payment placeholders (TASK-836) ([c9e52ef](https://github.com/kouroshez/coding-os/commit/c9e52ef15433091ff590d9f1c8aa4fceacf44019))
* **hub:** data-drive RolesPage agent picker + render single-integer model ids ([46424ab](https://github.com/kouroshez/coding-os/commit/46424ab1dcf9eecb06ba310bdfa8a682fa6d6e88))
* **hub:** harden /api/sessions payload + bound search sys.path & graph export (TASK-833) ([43c456a](https://github.com/kouroshez/coding-os/commit/43c456a58dbdce42076ab32895050b5ecaea6411))
* **hub:** honest telemetry + working Activity bell + Search redesign ([1523792](https://github.com/kouroshez/coding-os/commit/15237925fa6a292ec2ef836f9c3cee904f7323e9))
* **hub:** honor per-request project scope over ambient env in Hub routes ([83a9729](https://github.com/kouroshez/coding-os/commit/83a97294e1c8208ec520a6185b21969d7fb40b53))
* **hub:** InfoTip a11y (aria-describedby + Esc-dismiss); drop orphaned read-only comment ([144fcf0](https://github.com/kouroshez/coding-os/commit/144fcf0a89328bdea7dd098a5a03cf0cbe417ac4))
* **hub:** isolate scheduled run-now, honor cron hour, scope client logs (TASK-834) ([c30d648](https://github.com/kouroshez/coding-os/commit/c30d6488f64a3b74337639874ce364e61aa47491))
* **hub:** keep board toolbar and zoom controls clear of the stream/legend/tweaks panels ([ca567ef](https://github.com/kouroshez/coding-os/commit/ca567ef117224dd400e89af8799859f84b4e1b97))
* **hub:** keyboard-operable switch toggles + WAI-ARIA tablist nav (TASK-835) ([8dfe962](https://github.com/kouroshez/coding-os/commit/8dfe962da3617d59e181cd80a31936276565074d))
* **hub:** make Composer module chips authoritative and land users in the new project ([48b0121](https://github.com/kouroshez/coding-os/commit/48b012155fea6d19223c40c952f15a54e95b60db))
* **hub:** make HealthAlarmBar link scope-aware and reconnect LiveStatus SSE on project switch ([ece7d9a](https://github.com/kouroshez/coding-os/commit/ece7d9ac63b90c64d7509553d738e63d3d46ee33))
* **hub:** plain-language module refusal string + surface toggle cascade notes ([de28c5b](https://github.com/kouroshez/coding-os/commit/de28c5bc4701ae7eb681a04c06efcfa7a1758ade))
* **hub:** preserve task Work Log on board edit; focus deep-linked task; trim dead bell events ([f86404c](https://github.com/kouroshez/coding-os/commit/f86404cb6d448f80ff42f48784c1ffb07df6d619))
* **hub:** re-open the Composer when a create job is still running after a reload ([b9e2415](https://github.com/kouroshez/coding-os/commit/b9e24159110eaf631294f058f385aa67e961232c))
* **hub:** real per-session ctx badges for every adapter ([1d3e0bf](https://github.com/kouroshez/coding-os/commit/1d3e0bf6216ff10065a830d17eed3d1c3ebe3d64))
* **hub:** review fixes for config mutations — cos JSON parse, argv guard, cwd shadow ([1012152](https://github.com/kouroshez/coding-os/commit/1012152d61bd00e80a74fd1e2e7e5d32e3ef3157))
* **hub:** scope Config→Git settings per-project + preserve unknown sections + atomic write ([0a1c48c](https://github.com/kouroshez/coding-os/commit/0a1c48ce7ea4bc352fe4f6bdede38ccb39fb74f9))
* **hub:** stop Config→Git leaking meta-repo framing to consumers; fix NUL-byte separator ([ee02785](https://github.com/kouroshez/coding-os/commit/ee027857a77dcd4b7c2b9ae824388444e01c36ae))
* **hub:** stop the board "+ more" button re-fetching an exhausted column page ([641b0ba](https://github.com/kouroshez/coding-os/commit/641b0ba3fdd46ce9f26a8c6537ae5f9da2f96a70))
* **hub:** surface fetch failures on Diagnostics Overview and the Roles panel ([f65b5fd](https://github.com/kouroshez/coding-os/commit/f65b5fdbe22a5bdd68c60a1d19d26c743efc2d14))
* **learning:** emit enum-valid domain header on filed narratives ([c58ff38](https://github.com/kouroshez/coding-os/commit/c58ff385c6d6e96c6eaf735e741db16a1fd59a34))
* **learning:** link filed narratives to the real slugged task file ([cca0db4](https://github.com/kouroshez/coding-os/commit/cca0db43e2877861d996e00c49bb5da3cba87dee))
* **learning:** mine anatomy lessons from remedy-less backtracks via canonical remedies ([b3603bf](https://github.com/kouroshez/coding-os/commit/b3603bf3fa7829481eac64b4f540b2b6887ca09e))
* load Codex transcripts in Hub chat ([ba5b320](https://github.com/kouroshez/coding-os/commit/ba5b320d562d36e6dd42f73f99d20c677f512762))
* **memory:** drain embedding-outbox under rag interpreter + BGE-M3 similarity floor ([641a28a](https://github.com/kouroshez/coding-os/commit/641a28a8dc24d151745c08b98a877320d816ad6b))
* **memory:** hide mechanical capture rows as changelog + session-wide write-dedup ([be361e0](https://github.com/kouroshez/coding-os/commit/be361e0afb99849a6e7ad7b33bd44e482cce5aba))
* **memory:** recalibrate BGE-M3 memory floor 0.55-&gt;0.45 to restore synonym recall ([8f4b1a6](https://github.com/kouroshez/coding-os/commit/8f4b1a6ad3fb1e3e5ec328c4ea00d88aba433327))
* **memory:** relabel MEMORY.md trusted-lessons badge validated→seen ([8a85d69](https://github.com/kouroshez/coding-os/commit/8a85d69cc412de838f330863522d5817baccd738))
* **memory:** split conflated times_validated into times_seen vs times_validated (v49) ([eae440c](https://github.com/kouroshez/coding-os/commit/eae440c4b83439540ef52a52bd2be2041e20e6ea))
* migrate Codex hooks feature flag ([214128d](https://github.com/kouroshez/coding-os/commit/214128d9b5eafb9716127c3fcc09882f87dce116))
* **nightly:** reconcile orphan doc chunks + run memory_gc; column-guard gc ([625a14a](https://github.com/kouroshez/coding-os/commit/625a14a9baf960c31c79923a568a126acf7db94e))
* **node-express:** exclude test files from pre-install tsc typecheck ([d7ebfa4](https://github.com/kouroshez/coding-os/commit/d7ebfa462fed266f671452b4416addf113c2e41b))
* **onboarding:** keep readiness on one signal and stop json mode emitting prose ([b729f92](https://github.com/kouroshez/coding-os/commit/b729f9241cd1ee9ad39c2987ef8472f352da6880))
* **pr-mode,hooks:** preserve unpushed work on cleanup; anchor session-end advisory (H/J/N) ([f811816](https://github.com/kouroshez/coding-os/commit/f811816faedd476181eb90aab3210cf99a9559eb))
* **pr-mode:** cos pr cleanup preserves drifted/peer uncommitted work before destroy ([7cfb7de](https://github.com/kouroshez/coding-os/commit/7cfb7de879bc1bb0417fc3ae80d256d5eb330a45))
* **pr-mode:** driver STOP-on-green is signal-derivable via passing-unarmed (D5) ([e578778](https://github.com/kouroshez/coding-os/commit/e578778ca17fa2bf3eb24259784d6639057c5a9b))
* **pr-mode:** harden branch-guard double-prefix, gh-api cwd, reaper preserve (D1/D4/D2) ([5f65cf1](https://github.com/kouroshez/coding-os/commit/5f65cf19e5e412781889293ded74877b962f31a0))
* **pr-mode:** route misrouted worktree state to a per-worktree quarantine off the hub ([fe31593](https://github.com/kouroshez/coding-os/commit/fe315933d239abf3facccd9e3a525c1f88f21ed5))
* **pr:** distinguish merge-queue queued/ejected from pending in ci rollup ([9b4f407](https://github.com/kouroshez/coding-os/commit/9b4f407112cbeeea945abe61070c198875657a7d))
* **pr:** harden owner-stamp liveness — refresh on re-open, parse pid past a quoted host ([8c43b75](https://github.com/kouroshez/coding-os/commit/8c43b750576719d4f63e117dfb37d24f39fa0e37))
* **pr:** reaper skips a live-but-presence-less worktree via the lock-owner pid ([371ed93](https://github.com/kouroshez/coding-os/commit/371ed93306c301c3c0e1590a35b73a56e03b09ca))
* **pr:** surface review-required so auto_merge does not silently deadlock on reviews ([c32a5f7](https://github.com/kouroshez/coding-os/commit/c32a5f746d82b7e7be604007e3a178bd477de333))
* **pr:** validate autonomy_level at consumption + escalate auto-merge deadlock ([d9c47e2](https://github.com/kouroshez/coding-os/commit/d9c47e24e871065fc94c87c10bcda34147196160))
* **review:** apply code-review findings from the 9-task backlog (bugs + doc-drift) ([74d4394](https://github.com/kouroshez/coding-os/commit/74d43944107e4973e802d3b38ca3e611d170637e))
* **review:** apply ultra-code-review findings to the TASK-633..642 backlog ([76ea6f6](https://github.com/kouroshez/coding-os/commit/76ea6f63d8c74fcd48c5509334d27ac0347621d8))
* **review:** correct 6 bugs introduced by the code-review fix batch ([1ba0d7f](https://github.com/kouroshez/coding-os/commit/1ba0d7f356ea352bf88f1f4bcdeaa70b34f18031))
* **review:** RED test + test-modules coverage + regex/UI guards from max-effort review ([daace0b](https://github.com/kouroshez/coding-os/commit/daace0b3e8d7e7d52b8626959f8c0b2a72c572fa))
* **review:** relocate $HOME DB guard to init_db; board sends full body to keep Work Log ([955678c](https://github.com/kouroshez/coding-os/commit/955678c4ed50f3e3e4a424a7fe0a51296f13a83a))
* **review:** restore resolve_db_path raise as the complete $HOME guard; swap fresh Work Log on edit ([cee1116](https://github.com/kouroshez/coding-os/commit/cee1116c82e1ff4284322e26b7b501730b96352d))
* **scheduled:** nightly.py runs as a direct script — bootstrap src + src/core on sys.path ([5d3ec2a](https://github.com/kouroshez/coding-os/commit/5d3ec2a4ba6151165d982d8d8b55b72ddcc733c7))
* **templates:** astro problem.ts emits the canonical error envelope, not RFC 9457 ([8ae1f46](https://github.com/kouroshez/coding-os/commit/8ae1f46f6c8c0778c837121fc2ccf1e7b92ed6d2))
* **templates:** astro sample test passes astro check; pin Node&gt;=20 for global crypto ([2f25745](https://github.com/kouroshez/coding-os/commit/2f25745211cd3ab2eff2bf4bf22e7ac92dc9b564))
* **templates:** complete go-fiber v3 migration across docs, skill, rules, boundary ([635662b](https://github.com/kouroshez/coding-os/commit/635662b3e67d1abe155225841fc546b3dbe27165))
* **templates:** conform nestjs error filter and docs to the error-format.md envelope ([ea8efd8](https://github.com/kouroshez/coding-os/commit/ea8efd8b31bd9b2bc4430c26df0013528b162fab))
* **templates:** gate every task-system instruction in AGENTS.md fragments on modules.tasks ([04ff621](https://github.com/kouroshez/coding-os/commit/04ff621a380c4f5bd2fa65d5cebd60f508b38e9f))
* **templates:** honest verify + day-one sample tests for 5 stacks ([7d5cc3c](https://github.com/kouroshez/coding-os/commit/7d5cc3cd3ef63bd8ffaff65d4246f239e14c7e9b))
* **templates:** node-express verify command drops the dead npx-eslint prefix ([e2eaae3](https://github.com/kouroshez/coding-os/commit/e2eaae361edfad2d2451d3c316164cb6e594ff17))
* **templates:** relocate wordpress skill to its stack overlay (stop over-shipping) ([4c6b6e0](https://github.com/kouroshez/coding-os/commit/4c6b6e0d4fc5cbfcd3cb293f149c6fd6a6d651b4))
* **templates:** remove go/go-fiber/svelte shipped-artifact drift ([18667a1](https://github.com/kouroshez/coding-os/commit/18667a13a524b847ebcd923877f0b5470de11dd4))
* **templates:** repair 4 shipped hard-breaks (dangling rules, go-fiber v3, mvnw, astro content-seo) ([3854a0a](https://github.com/kouroshez/coding-os/commit/3854a0a71290da6244b5b30bff73438ae06cfb2c))
* **templates:** ship angular accessibility doc for the playbook's a11y link ([76a8931](https://github.com/kouroshez/coding-os/commit/76a8931ed33837d184910944b9e16c5eade69aee))
* **templates:** ship aspnet-core xUnit test project for green dotnet test on init ([b5481aa](https://github.com/kouroshez/coding-os/commit/b5481aa3e7643294aceaa6a1d2f88f868acff29e))
* **templates:** ship go-fiber go.sum so go vet/test pass on a fresh init ([91e5d25](https://github.com/kouroshez/coding-os/commit/91e5d256a6b8838791cb0d0debeb1ba63d2ee3c0))
* **templates:** spring-boot scaffold google-java-format + bind spotless to verify ([9cfdfb8](https://github.com/kouroshez/coding-os/commit/9cfdfb880bae277d8b3b4276cbe72c42a4c33d14))
* **templates:** svelte vite.config import + vue-nuxt vitest/vite major skew ([ee42c5f](https://github.com/kouroshez/coding-os/commit/ee42c5fe3dc8a0b0a853197aa48d3783cc38713a))
* **templates:** sync nextjs/wordpress verify substitutions + revert day-one-red changes ([37a7783](https://github.com/kouroshez/coding-os/commit/37a7783b6dbcb1b02e1991b2bfae23218340995d))
* **templates:** wire cross-adapter Channel-2 memory-read pointer into AGENTS.md ([90284bd](https://github.com/kouroshez/coding-os/commit/90284bd5e3d4eb44dfbd3cc6a2fc083190fd526e))
* **test:** -S in nightly smoke test so the editable finder can't mask a broken bootstrap ([5fcf70e](https://github.com/kouroshez/coding-os/commit/5fcf70e75e3728e5c17dbb82ab655bc74b0ffbea))
* **thinking_os:** atomic observation dedup via partial UNIQUE index (migration v51) ([dcf15b3](https://github.com/kouroshez/coding-os/commit/dcf15b3141676ff6a6229b6152007fe26ba20721))
* **thinking_os:** close the learn-validate loop on the MCP completion path ([5378bc9](https://github.com/kouroshez/coding-os/commit/5378bc95d16dc01e8bde52a608bc75a49cf6b840))
* **thinking_os:** session_summary bootstraps src/ so it runs as a file ([90780f1](https://github.com/kouroshez/coding-os/commit/90780f19e6aed3fdaa9be87663ca0a24990f0584))
* **web:** attribute unowned panel move/reposition to the human actor ([8c70fb1](https://github.com/kouroshez/coding-os/commit/8c70fb1dde37a5073af79e408e821aa59216c748))


### Performance

* **core:** guard jit-nudge mkdir behind a dir-exists check ([e4ab25d](https://github.com/kouroshez/coding-os/commit/e4ab25d264d8b78f3866d60afd7ef108e6906298))
* **pr:** reaper sweep lists worktrees once (O(N)) and rejects foreign-host owners ([cc31900](https://github.com/kouroshez/coding-os/commit/cc31900e2f10761bef0e07afc39b030875279425))
* **tests:** class-scoped scaffold for TestInit + TestClaudeAdapter (cos-init once per class) ([3f22dab](https://github.com/kouroshez/coding-os/commit/3f22dab9364600c0c08de1e197e8da307b647173))


### Changed

* **board:** self-documenting names over comments in board_coherence ([55974f8](https://github.com/kouroshez/coding-os/commit/55974f893c511e69b441ec914f3e21bcf4373462))
* **core:** compress git-workflow, test-discipline, transparency-banner rules 42 percent ([dce452b](https://github.com/kouroshez/coding-os/commit/dce452b6e27cf34fca22072456e79cedbf74fc14))
* **core:** disjoin graph_query/graph_search + honest kernel always-on tool floor ([0d12e76](https://github.com/kouroshez/coding-os/commit/0d12e762a053cf17e30a774ae7f5788531c7b471))
* **core:** drop dead completion_gap read-paths + cos_learn_feedback; measured [Memory] pulse ([5192ef9](https://github.com/kouroshez/coding-os/commit/5192ef970c4f023407e7153da4a0972abe6397be))
* **golden:** single SECTIONS SSOT module for capture + parity test ([bf4ff33](https://github.com/kouroshez/coding-os/commit/bf4ff33605efab628d71a9b3fe821ce80b8f5215))
* **hooks:** behavior-parity harness + delete transitional warn-template-drift hook ([d82ffdc](https://github.com/kouroshez/coding-os/commit/d82ffdccac7e05c500632ece77d3dc2c46d7ba5e))
* **hooks:** consolidate branch_guard onto shared tokenizer + fail-closed test ([0fb3de0](https://github.com/kouroshez/coding-os/commit/0fb3de0e1c491e67145c55f4749d7b91489aacaa))
* **hooks:** merge shell reindex+prune into one ordered reconciler (cluster 4) ([1eb8041](https://github.com/kouroshez/coding-os/commit/1eb80414f3efb4937a75cdd19a1199bf18fd4b5a))
* **hub:** decompose ChatView (806L) into chat-turns + chat-turn-views (TASK-836) ([f631c23](https://github.com/kouroshez/coding-os/commit/f631c232ec431adf48fb2783693b23a89e930ae9))
* **hub:** decompose ConfigPage (1855L) into features/config modules (TASK-836) ([37b8f79](https://github.com/kouroshez/coding-os/commit/37b8f79c8f374ed827ca6e18ece4d92c177a40a9))
* **hub:** derive the scheduled-endpoint payload types from the OpenAPI schema ([d055f4f](https://github.com/kouroshez/coding-os/commit/d055f4fdde811add3a8e24257cd9639c4e570505))
* **hub:** extract board modals/badges/panels from CosBoardPage (TASK-836) ([379bb3f](https://github.com/kouroshez/coding-os/commit/379bb3f7fbe327f8ea7b5bb2ac65d9d65dbecb59))
* **hub:** extract board-shared (types/constants/helpers/context) from CosBoardPage (TASK-836) ([e704ee2](https://github.com/kouroshez/coding-os/commit/e704ee232c73fc7ce51fb19c7c686987da0a7e3d))
* **hub:** extract git-tab-data (types/presets/tips) from GitTab (TASK-836) ([77da2d3](https://github.com/kouroshez/coding-os/commit/77da2d381d0a9be940e52df041a3b256935b18b2))
* **hub:** extract TaskDetailDrawer + history into task-detail from CosBoardPage (TASK-836) ([e04b50d](https://github.com/kouroshez/coding-os/commit/e04b50d91f0e739cb44e7a5d5fb0f474a426ded0))
* **hub:** extract TaskStickyCard/SwimlaneLabel + TopBar from CosBoardPage (TASK-836) ([f00ded8](https://github.com/kouroshez/coding-os/commit/f00ded827e229120236bf37983f8bce0dee594dd))
* **hub:** extract the stream-event and trace-timeline models from their views ([094448c](https://github.com/kouroshez/coding-os/commit/094448cde6de91ffc5fac704e1e72176edcee00d))
* **hub:** route MemoryPage/DoctorPage through api-client (TASK-836) ([489baf2](https://github.com/kouroshez/coding-os/commit/489baf25e9e46d492cea25d0620ce5af1509e6d6))
* **hub:** split board-modals into 4 modules all &lt;400 (TASK-836) ([6f6956c](https://github.com/kouroshez/coding-os/commit/6f6956c5a37b1f5e5156b99df67c9d98452c5f2a))
* **hub:** split board-panels into 4 panel modules all &lt;400 (TASK-836) ([8be4f2e](https://github.com/kouroshez/coding-os/commit/8be4f2ecfe6e214b793ca0c88ac9b214c0d0fa84))
* **hub:** split CosBoardPage into data/view/dnd hooks + grid — main 928-&gt;233 ([4b1f82c](https://github.com/kouroshez/coding-os/commit/4b1f82cdb5f9b7c8b03fa6b460a61c7ec5fadbef))
* **hub:** split task-detail drawer + GitTab so every module is under 400 lines ([5a74c51](https://github.com/kouroshez/coding-os/commit/5a74c51038bd9543684b3dcbe553c3d35ad051ba))
* **hub:** split task-detail into drawer + history + edit-form (TASK-836) ([4be988d](https://github.com/kouroshez/coding-os/commit/4be988d280864b4727809841342ab3d575a3f627))
* **thinking_os:** drop dead record_review + auto-record memory-check on cos_search ([78b6176](https://github.com/kouroshez/coding-os/commit/78b6176d776035eeaf986b28cf21978d958729e8))


### Documentation

* **adapters:** define current Codex capability and SDK contract ([3aca2b2](https://github.com/kouroshez/coding-os/commit/3aca2b2798ef7df61a52f02a221f6079ec1729f1))
* **adapters:** state the enforced P8 boundary and sanctioned lazy-import carve-out ([fc54993](https://github.com/kouroshez/coding-os/commit/fc54993328e354b92315b52bb6b9b8b282790be3))
* **adr:** ADR-0014 unified graph-gate + graph-first-enforcement epic tasks ([eb47932](https://github.com/kouroshez/coding-os/commit/eb47932c6b5083db15ffff9b2ddcf4f469b9fea6))
* **adr:** kernel scope boundaries (ADR-0015) + dispatch-deferral partially revived ([525c258](https://github.com/kouroshez/coding-os/commit/525c25841af551455b75879c50d277784120918a))
* **adr:** record graph-first-enforcement landed C1-C5; scope C6 deferral ([ec6e02a](https://github.com/kouroshez/coding-os/commit/ec6e02ae2e906c7c32531116fc35b7a8ddfa2c24))
* align public-facing docs with current reality before first release ([0e64f46](https://github.com/kouroshez/coding-os/commit/0e64f463a9a085ddd418f6a37635f03866cef2db))
* **api:** regenerate openapi.json — spec drifted from live routes ([d97eee5](https://github.com/kouroshez/coding-os/commit/d97eee55ed8a611df5f5d50c12341bf37d80251c))
* **architecture:** complete raptor lens — density, operational cost, worked case study ([e0dc8f8](https://github.com/kouroshez/coding-os/commit/e0dc8f8217bd91cf54609356f3a85e2f874fc23d))
* **core:** align dispatcher contract with current Codex runtimes ([e3f6d5b](https://github.com/kouroshez/coding-os/commit/e3f6d5bc0b0de62e32c9a76fa3c257e876f6553a))
* **engineering:** July 2026 modularity re-audit + variability-completion backlog ([1e1d849](https://github.com/kouroshez/coding-os/commit/1e1d84917de0b1fade145cfac9663a849c882972))
* **engineering:** register derived-store coherence audit in the index ([4db6472](https://github.com/kouroshez/coding-os/commit/4db64723dc7954d9bc30739ed3ab51d64b0f62d5))
* fix onboarding clone URLs and stale governance references ([7487fa7](https://github.com/kouroshez/coding-os/commit/7487fa724f22633918ec40bf54e68fcc9a36c9f6))
* **governance:** add Critical Rule 26 — verify by executing, not by reading ([153b5ec](https://github.com/kouroshez/coding-os/commit/153b5ec725190f8dc4c11bf4de8e33ebd58b5f88))
* **governance:** add product vision + raptor consolidation lens as SSOT docs ([4b5b8b4](https://github.com/kouroshez/coding-os/commit/4b5b8b41b5561b3c60559b7197148b06009be25c))
* **hub:** tick-by-tick pre-release audit report for the Hub UI ([4b5b00b](https://github.com/kouroshez/coding-os/commit/4b5b00bfa6161f9223b7732cb63ddb9233a5c9fc))
* **index:** commit stale auto-index regen for adapters + engineering ([6f81c8f](https://github.com/kouroshez/coding-os/commit/6f81c8f6f53d1a6381cc9999789f55b4034721f6))
* **index:** list pr-mode-ci-economics playbook in the auto-index (TASK-619) ([47615ab](https://github.com/kouroshez/coding-os/commit/47615ab20488c361159fd14bcec4862f509d93d9))
* **index:** re-sort engineering index for the modularity-audit updated date ([48ed52a](https://github.com/kouroshez/coding-os/commit/48ed52a96053408e4b0d557fd0742bb921e1df03))
* **memory:** mark QW-3 shipped as detector, not column (SSOT) ([be697a6](https://github.com/kouroshez/coding-os/commit/be697a6522125dcb2ae1a4398c1cc045e90bae04))
* **memory:** persist icebox-parking structural-failure finding ([288de5f](https://github.com/kouroshez/coding-os/commit/288de5fb85e2195f11858a8ce185afbe0100df7c))
* **memory:** reconcile memory.md + retro.md with the shipped memory/metrics tools ([79f4e27](https://github.com/kouroshez/coding-os/commit/79f4e270000deff6224439a091fc893fe1192331))
* **modularity:** record pass-7 audit + inline the tasks-&gt;docs rationale ([620a0db](https://github.com/kouroshez/coding-os/commit/620a0db06157c20fd87ae4fb9dedec549858f8b5))
* **onboarding:** document the panel-first install path and the module/profile axis ([79a5026](https://github.com/kouroshez/coding-os/commit/79a502612ea215d13b9026ad2db0c37ccc514512))
* **playbook:** add multi-agent git layered-defense model + 11 real-world use-case matrix ([0893477](https://github.com/kouroshez/coding-os/commit/089347713471b198e0a0373c143fbfaa3bed2654))
* **pr-mode:** document agent-only enforcement boundary + settings durability ([7b8d9d8](https://github.com/kouroshez/coding-os/commit/7b8d9d8606a753572bd99ba8c8ad40a5783d4045))
* **pr:** pr-mode CI economics — fast-gate/full-suite split + reference workflow ([c41e84d](https://github.com/kouroshez/coding-os/commit/c41e84d45c9b2f892b830afa6f9587cf20973577))
* research multi-adapter supervisor architecture ([1254119](https://github.com/kouroshez/coding-os/commit/1254119d46e03af39f629fd4db259b977e364673))
* **rules:** add Test cadence policy to test-discipline.md ([d07f6e8](https://github.com/kouroshez/coding-os/commit/d07f6e806d2a28e9bedc23973775244ee421e59f))
* Smoke row in testing-strategy + the as-file bootstrap invariant in scheduled-jobs and hook-authoring. Regenerated golden (hook + skill drift). ([e1090cb](https://github.com/kouroshez/coding-os/commit/e1090cb603e7855b40d144a3c1ce5a7bb2b7a8db))
* **templates:** add references/anatomy.md to 13 bare stack skills ([d4c91b9](https://github.com/kouroshez/coding-os/commit/d4c91b9f555cf3c3b1e866d48532fa1fac3e6a5b))
* **test:** refresh stale suite-size figures to ~4,850/327 files ([e03f87c](https://github.com/kouroshez/coding-os/commit/e03f87cfa804ffec030cf5f4ab8c3e1289f1a77f))
* **tests:** testmon spike verdict — DEFER (redundant with verify-ledger dedup) ([e7c6dba](https://github.com/kouroshez/coding-os/commit/e7c6dba918158799dbb09f8a30050408364643c9))


### Build

* pin ruff==0.15.15 — floating pin broke the CI format gate on each release ([ec1f607](https://github.com/kouroshez/coding-os/commit/ec1f6078ab4f376110896cb3b84981a28dfaf226))

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

---

## [0.3.0] — 2026-05-20

Initial public release of **coding-os**, the agent-agnostic cognitive
operating system for AI coding agents.

### What is coding-os?

Three-layer composition that teaches AI agents *how to think* and
*how to code*:

- **`src/core/`** — agent-agnostic kernel: MCP server (`thinking_os`,
  `graph_os`, `board_os`), hooks (62 scripts), rules, skills.
- **`src/adapters/<agent>/`** — per-agent translation: how the kernel
  surfaces as `.claude/`, `.codex/`, `.cursor/`.
- **`src/templates/<stack>/`** — per-stack scaffolds: Django, Next.js,
  FastAPI, Go, Go+Fiber, React Native, Python library, Meta.

The `cos` CLI composes the three layers into a consumer project that
inherits the same skeleton (own hooks, own MCP, own `AGENTS.md`).

### Highlights of the 0.3 line

#### Cognitive layer (`thinking_os` + `graph_os` + `board_os`)

- 11 semantic agent roles (researcher, analyst, architect, documenter,
  implementer, reviewer, debugger, security_auditor, deployer,
  observer, refactorer) composable via `cos_compose_chain`.
- Append-only schema migrations with idempotent extractors.
- Polyglot graph extractor: Python, TS/TSX, Go, Bash, YAML, Markdown,
  JSON, TOML. Parallel reindex (`cos graph-reindex --workers N`).
- Knowledge graph backed by SQLite (Kuzu backend retired in B2 series
  — see ADR 02).
- 79 MCP tools, all under the `cos_*` prefix with the
  `ok(data) / fail(category, message)` envelope (Rule 13).

#### Workflow governance

- Intent enforcement layer: exhaustive-intent vocabulary (FA + EN)
  triggers evidence-required audit mode (G0–G14).
- Completion guardian (Stop hook) refuses premature "done" claims
  without satisfying predicates.
- Scrumban task system (`docs/tasks/TASK-*.md`) with axes:
  swimlane · kind · epic · labels. WIP-limit enforcement.

#### Web Hub

- Singleton FastAPI + uvicorn on port 9188, multi-project router via
  `/api/p/<slug>/*`. SSE event stream at `/api/stream/events`.
- React 18 + Vite + TypeScript + Sigma.js graph canvas + Zustand state.
- 4 tabs: Graph (3 views — overview/tree/code), Board (Scrumban),
  Cognition (trace replay), Search.
- All `/api` responses ≥ 500 B gzipped (compresses 270 KB → 21 KB).

#### Adapter parity

- Adapter capabilities declared in
  `src/adapters/<agent>/adapter.yaml::hook_capabilities` — renderer
  skips registry entries the agent's CLI can't fire.
- Claude Code: 58/62 hooks fire. Cursor: 59/62. Codex CLI: 21/62
  (Bash-only). Codex GUI: 0/62 (`.codex/hooks.json` ignored upstream).
  *(Historical — the Cursor adapter was removed 2026-06-15 and Codex
  reached full hook parity 2026-08-03; current matrix:
  [adapter-parity.md](docs/engineering/adapter-parity.md).)*

#### Performance

- Database mmap + `ANALYZE` on init → 4× faster JOINs.
- Nightly auto-reindex when graph probe > 24 h stale.
- Barnes–Hut FA2 layout cuts graph-tab freeze from 10–30 s to < 2 s.
- Hook timeouts capped at ≤ 30 s (previously up to 5000 s).

#### Repo hygiene (this release)

- Apache License 2.0 + NOTICE.
- SECURITY.md private-disclosure policy.
- CONTRIBUTING.md + CODE_OF_CONDUCT 2.1.
- `.github/workflows/ci.yml` matrix CI on every PR.
- `pyproject.toml` `[tool.ruff]` + `[tool.mypy]` baseline.
- `.github/dependabot.yml` (Python uv, npm, actions).
- `.pre-commit-config.yaml` (ruff + shellcheck + prettier).
- 5 ADRs documenting the major architectural decisions of the 0.x line.

### Removed in 0.3.0

- Internal client references (`NakoDigital`) replaced with neutral
  `ExampleApp` placeholders across scaffold templates, golden
  fixtures, and the E2E verification script.
- Developer-local path defaults in `verify_phase_c_e2e.py`; the script
  now requires `COS_CORPUS_PATH` explicitly.
- Internal experiment artifacts predating the 0.3.0 baseline (see note
  at top of file).

### Acknowledgements

- The thinking_os methodology draws on John Boyd's OODA loop, the
  Cynefin framework (Snowden), Wardley Mapping, and DDD bounded
  contexts.
- The graph_os layer draws on Roy Fielding's REST dissertation,
  tree-sitter, and the GraphRAG literature.

[Unreleased]: https://github.com/kouroshez/coding-os/commits/main
[0.3.0]: https://github.com/kouroshez/coding-os/tree/c4166d9d39b9f4c781883aa8bf7f51ddbc33b403
