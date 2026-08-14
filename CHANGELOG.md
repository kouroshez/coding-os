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

## [0.3.19](https://github.com/kouroshez/coding-os/compare/v0.3.18...v0.3.19) (2026-08-14)


### Fixed

* **hub-ui:** picking a project no longer bounces chat and memory to Hub home ([a3eaa3c](https://github.com/kouroshez/coding-os/commit/a3eaa3c66720c44e7f549218497a8ae5546babd0))
* **hub:** say codex live chat is unbuilt instead of explaining in-process streaming ([f86e047](https://github.com/kouroshez/coding-os/commit/f86e0471b868c157968a344cf47c865bca28aacc))


### Documentation

* **readme:** show the Web Hub with five annotated screenshots ([bd3aa8e](https://github.com/kouroshez/coding-os/commit/bd3aa8e365faa8ba3dc4986bef4e4d9dca0e1475))

## [0.3.18](https://github.com/kouroshez/coding-os/compare/v0.3.17...v0.3.18) (2026-08-14)


### Fixed

* **templates:** pin log4j2 2.25.5 in the spring-boot scaffold for CVE-2026-49844 ([c6be65d](https://github.com/kouroshez/coding-os/commit/c6be65d7750e6005972cb96ec5d5672aa958001b))


### Documentation

* **governance:** turn the PyPI approval gate off and record why the reversal is the lesson ([fa3a087](https://github.com/kouroshez/coding-os/commit/fa3a087d23516f3919509239b70a0cad7c4edea1))


### Build

* **security:** hash-pin the build frontend and verify the uv installer before running it ([e676d5b](https://github.com/kouroshez/coding-os/commit/e676d5b678ebdbea5a3ba9862ec66d9c1e314bec))

## [0.3.17](https://github.com/kouroshez/coding-os/compare/v0.3.16...v0.3.17) (2026-08-13)


### Documentation

* **agents:** add the Verification-Matrix row for src/core/rules and src/core/skills ([1bd26e7](https://github.com/kouroshez/coding-os/commit/1bd26e78666bb07d66352cf337e47a98d3fcb767))
* **governance:** gate irreversible publishes behind a human, and say why review cannot be bought here ([7a0d27d](https://github.com/kouroshez/coding-os/commit/7a0d27d36c780cd00da60b4b5b91e72ec78f7170))

## [0.3.16](https://github.com/kouroshez/coding-os/compare/v0.3.15...v0.3.16) (2026-08-13)


### Fixed

* **deps:** bump nanoid to 3.3.18 for GHSA-2v37-7h3g-55p8 ([6a4ad9d](https://github.com/kouroshez/coding-os/commit/6a4ad9d0a7bb9a841cb0dcb5d53eb08eca98c2fc))


### Documentation

* **ci:** correct the Signed-Releases prediction with the measured result ([f76a359](https://github.com/kouroshez/coding-os/commit/f76a3591085ef103a6873ca9b60127bb0e852cb3))

## [0.3.15](https://github.com/kouroshez/coding-os/compare/v0.3.14...v0.3.15) (2026-08-13)


### Fixed

* **board_os:** freeze the clock in the reconcile determinism test ([4615982](https://github.com/kouroshez/coding-os/commit/461598285ccdafaff26c069d4950e2013702bd8b))
* **ci:** drop the unused noqa that failed the ruff gate ([c8dec8e](https://github.com/kouroshez/coding-os/commit/c8dec8eff3449cb63e90b733469e18e720015f81))
* **ci:** make Dependabot able to satisfy the gates this repo already has ([05c93d3](https://github.com/kouroshez/coding-os/commit/05c93d3b67c6c5c012af17b24bbb6755587c350d))
* **ci:** set the mypy baseline from the CI count, not the local one ([bbb39fd](https://github.com/kouroshez/coding-os/commit/bbb39fd0031da1c327a910b8d443b215475ed021))
* **deps:** clear all 79 OSV advisories across scaffolds and locks ([c7cab87](https://github.com/kouroshez/coding-os/commit/c7cab878fe732565f6280a60a0e35750f49872c9))
* **graph_os:** use SHA-256 for the three derived content digests ([41946cf](https://github.com/kouroshez/coding-os/commit/41946cf92f378b537f5ed46e8d1b8b9d40e5b35b))
* **release:** bump uv.lock with pyproject.toml and gate the drift in CI ([912f902](https://github.com/kouroshez/coding-os/commit/912f9025d032e9c19606dd9b76f1401fa7cee3d7))
* **security:** close the weak-hash, ReDoS and URL-substring CodeQL alerts ([ba37021](https://github.com/kouroshez/coding-os/commit/ba37021f9e1063c6acba315d533c65f05a3f03bb))
* **security:** log exceptions under a correlation id instead of returning str(exc) ([7fbffcb](https://github.com/kouroshez/coding-os/commit/7fbffcb530eafe185b55db2821eb8e1e76d00d55))
* **security:** one path-segment validator, applied where request data joins a path ([cf343c3](https://github.com/kouroshez/coding-os/commit/cf343c3ec5743fd6b2b63805a8c0594d85507a01))
* **web:** drop the control-char regex class that broke the ESLint gate ([b670471](https://github.com/kouroshez/coding-os/commit/b67047117b66133302aaad7a4faf553df33ac79e))
* **web:** escape quotes and gate URL schemes in the task markdown renderer ([c596947](https://github.com/kouroshez/coding-os/commit/c596947b79903ae646e58b7ed1403ac854eba4bd))


### Changed

* clear the SIM105, SIM102 and E741 burndown ignores ([#30](https://github.com/kouroshez/coding-os/issues/30), [#31](https://github.com/kouroshez/coding-os/issues/31), [#32](https://github.com/kouroshez/coding-os/issues/32)) ([c2dc381](https://github.com/kouroshez/coding-os/commit/c2dc381ef0798c8776b3eb7180b7514fab8acfc2))


### Documentation

* **bench:** publish the Django 5.2 third-party token-cost row ([#37](https://github.com/kouroshez/coding-os/issues/37)) ([c51ecea](https://github.com/kouroshez/coding-os/commit/c51ecea59a9fc9e626e3f0fc51afd682e8e81fc3))
* **ci-gates:** record the CodeQL fix-vs-dismiss policy and the reachability test ([ad6b4d9](https://github.com/kouroshez/coding-os/commit/ad6b4d9ce42c2c6d6305168b2e543c7dc09b56cd))
* **ci-gates:** record the measured 5.9 to 7.4 outcome, not the prediction ([7dc5ce4](https://github.com/kouroshez/coding-os/commit/7dc5ce4592ad61287c88b0473e1c6ca91b9c048e))
* **ci-gates:** record the Scorecard weight model and its honest ceiling ([41288b0](https://github.com/kouroshez/coding-os/commit/41288b0cfa854045d53e5c7cda86803cb55bd16c))
* **insights:** record that fixing a CodeQL finding and clearing its alert are separate jobs ([9f23636](https://github.com/kouroshez/coding-os/commit/9f236363dcb330c855a3f03ebac45f457998a1c9))
* **insights:** record why a gate below a self-healing command is a no-op ([6fa4869](https://github.com/kouroshez/coding-os/commit/6fa4869942379a67a87c684f049618cb9811bf04))
* **release:** define the merge trigger and correct the pre-1.0 bump table ([fb006ca](https://github.com/kouroshez/coding-os/commit/fb006ca477c35ddb0aa7b7366fc5e28711e5462f))


### Build

* pin Docker base images by digest and the release build backend ([a63730e](https://github.com/kouroshez/coding-os/commit/a63730e9853a841353cfaf22a4011e57869cb5fa))

## [0.3.14](https://github.com/kouroshez/coding-os/compare/v0.3.13...v0.3.14) (2026-08-12)


### Fixed

* **scripts:** point the session-resolver probe at the helper's real module ([f6105a6](https://github.com/kouroshez/coding-os/commit/f6105a628cc50c21ab4ab8139ba2e11ef14bb617))
* **tests:** make the script smoke test catch sys.path bootstrap bugs ([4117200](https://github.com/kouroshez/coding-os/commit/4117200bbea1998bd8c06ea17a2127a1268b9312))


### Changed

* **scripts:** point the session-resolver probe's docs at the real module ([d9d7b0b](https://github.com/kouroshez/coding-os/commit/d9d7b0b256fe436e0b3e614818f009fc007f6d33))

## [0.3.13](https://github.com/kouroshez/coding-os/compare/v0.3.12...v0.3.13) (2026-08-12)


### Added

* **ci:** add zero-tolerance mypy error codes above the count ratchet ([dcb5b59](https://github.com/kouroshez/coding-os/commit/dcb5b594555180b5fe43ab547f407350e935724f))
* **cli:** offer quick vs custom setup and close init with an actionable panel ([bd008b7](https://github.com/kouroshez/coding-os/commit/bd008b7625891cf912250915ad9e7935abc50c39))
* **cli:** tell consumers which command actually upgrades coding-os ([16f38a5](https://github.com/kouroshez/coding-os/commit/16f38a5accceae7bb593bf0d33a55ed6c096fede))
* **hooks:** make the documented 300-line budget visible at write time ([03223e2](https://github.com/kouroshez/coding-os/commit/03223e2ed09a1ee42a861b0db03280596d357d8a))
* **hub:** list MCP servers by scope and accept custom http/sse servers ([e80a3c8](https://github.com/kouroshez/coding-os/commit/e80a3c8025fc8754f6d53780165db7ac3bd89026))
* **hub:** manage MCP servers per adapter, per scope, on both transports ([d1bbe50](https://github.com/kouroshez/coding-os/commit/d1bbe5091a003225230c7a371b2d6b77ae2ce74e))
* **hub:** probe adapter chat, dispatch and transcript capability at runtime ([2b5c611](https://github.com/kouroshez/coding-os/commit/2b5c611b2ae8fee873f2a2c4a36d57d14062a84c))
* **hub:** rebuild the Memory tab around the trust ladder ([65cb794](https://github.com/kouroshez/coding-os/commit/65cb7943ed9b8799ca08d680b96b30f80cd78b02))
* **hub:** show role titles and name what each inherited default resolves to ([452172a](https://github.com/kouroshez/coding-os/commit/452172a1b9fe891567cbb93d179c9a0aa8b99477))
* **rules:** add Critical Rule 27 — runtime cost is correctness ([6cb07ef](https://github.com/kouroshez/coding-os/commit/6cb07efa44d1477f3a4436b14e896bd3927ca07f))
* **scripts:** add a split-parity guard that proves a module move edited nothing ([1b1f508](https://github.com/kouroshez/coding-os/commit/1b1f50808b183d03192b85c39a86358de0ecf046))


### Fixed

* **ci:** annotate the split fixtures as generators so the mypy ratchet holds ([a594051](https://github.com/kouroshez/coding-os/commit/a59405124acfaced4ef5229f28f62a86b9d51b2d))
* **ci:** make dispatch readiness assertions environment-independent ([1bf6166](https://github.com/kouroshez/coding-os/commit/1bf61665d0e779d59d289aa4d1f2a722b010fbc3))
* **ci:** repoint the workflow, Makefile and scan-ignore paths at the split test modules ([072b009](https://github.com/kouroshez/coding-os/commit/072b0097a22893619f81c424da5e776eac477924))
* **ci:** resolve the remaining flat sibling imports for mypy ([004fd5b](https://github.com/kouroshez/coding-os/commit/004fd5b17d0ee5fae13c60e0b46aa4168d41c704))
* **ci:** restore the mypy BASELINE to the CI-measured value ([3283e41](https://github.com/kouroshez/coding-os/commit/3283e41813b411dd684d53c51b980b0a68e0cde1))
* **ci:** silence the flat-sibling import class for board_os and thinking_os tool modules ([d153222](https://github.com/kouroshez/coding-os/commit/d153222b82463b67ad1c98b2cdaa5451fe37e921))
* **ci:** spell out the flat-sibling mypy overrides so the dead glob stops hiding errors ([29a1eab](https://github.com/kouroshez/coding-os/commit/29a1eab1fbb4aba4ca33df399688300c6721e481))
* **cli:** register every command before the __main__ guard runs ([311aeb2](https://github.com/kouroshez/coding-os/commit/311aeb227a8db475f3ca80d84953af3947944049))
* **cli:** restore the dropped return in _normalized_hook_map ([d76583f](https://github.com/kouroshez/coding-os/commit/d76583fb3f2b701927cf2533f75af63cd57acd12))
* **docs:** repair three Verification-Matrix rows that resolved to no tests ([80a6293](https://github.com/kouroshez/coding-os/commit/80a6293166452253c83ecfd785dd9192ae0206fa))
* **gates:** measure the mypy count over kernel source, not test preambles ([b2b80aa](https://github.com/kouroshez/coding-os/commit/b2b80aa538bdee1f0139fda7fd0df37e4b4757fc))
* **graph_os:** drop the duplicated _php_short_name left by the contracts split ([1503226](https://github.com/kouroshez/coding-os/commit/1503226e9cc585161c02c12459bbe083c29b0338))
* **graph_os:** roll back the write transaction when a backend statement raises ([028196b](https://github.com/kouroshez/coding-os/commit/028196bf3d4cbbb8ee0aba30d8eb037407d094cb))
* **hub:** name the graph doctor tab and label its informational findings ([e5d41a3](https://github.com/kouroshez/coding-os/commit/e5d41a3e70e96e03d998b3ba54d38d7e9066dd28))
* **hub:** start the daemon without project- or session-scoped COS_* env ([cadaaa2](https://github.com/kouroshez/coding-os/commit/cadaaa2e78de417c2ad8e8b00ac799f8df0a9ff2))
* **memory:** render distilled lessons in the agent-memory mirror, not block counters ([ba79946](https://github.com/kouroshez/coding-os/commit/ba79946c2d7dc507765f9194e16a222b27d9b402))
* **memory:** sweep orphaned outbox rows so the embedding drain stops starving ([5c809ae](https://github.com/kouroshez/coding-os/commit/5c809ae414fab67fa3be0f36a5d70de17c7f0e0e))
* **mypy:** bind the strict overrides to the module names mypy derives ([0489c6d](https://github.com/kouroshez/coding-os/commit/0489c6d716ccee764209c46df31625f4671a0cbb))
* **presence:** restore the chat presence probe globals a module split left behind ([08d0b65](https://github.com/kouroshez/coding-os/commit/08d0b651a254b3a83dc49f2989be8a225390d6d6))
* **release:** unblock CI — regenerate api-types, split db pool, clean shellcheck ([68f2d2b](https://github.com/kouroshez/coding-os/commit/68f2d2b9ae4d781ef4d2a05d0953def51defcba1))
* **skills:** drop the live model id from the no-hardcoding example ([91f1fbe](https://github.com/kouroshez/coding-os/commit/91f1fbeb2c38d3bf97738adaef0159b04bd4d056))
* **tests:** assert sqlite3.Error so the rollback guard passes on 3.11+ ([c179e6b](https://github.com/kouroshez/coding-os/commit/c179e6b1884d0c15075a7f08441b87335c7a624c))
* **tests:** keep the cos-env marker-parity assertion within its size ratchet ([9e27c13](https://github.com/kouroshez/coding-os/commit/9e27c13a3dfa17ea75abf5c6a548f2ad3d6ea919))
* **tests:** repoint the assertions the cos-env and config splits moved ([3ac4da3](https://github.com/kouroshez/coding-os/commit/3ac4da3d6454dc8fffd597f5e6c9c40fcfe6273e))
* **update:** re-register hooks in the agent settings file when it falls behind ([47c7030](https://github.com/kouroshez/coding-os/commit/47c70304cff3bbe8136312fb1766b57e5b77b148))
* **update:** stop cos update relinking skills the project opted out of ([0f8adc4](https://github.com/kouroshez/coding-os/commit/0f8adc4db299092dfc3bdd95e7b64ec0e210a6d7))
* **web:** keep the cognition helpers reachable and patchable after the split ([76f46c1](https://github.com/kouroshez/coding-os/commit/76f46c1e66c23cbc2df93fd7f09ae1a4ac5294f0))
* **web:** re-export the moved cognition helpers from the facade ([d753929](https://github.com/kouroshez/coding-os/commit/d75392926ce0c92790b220c7b8f7ae542346440b))


### Changed

* **board_os:** split id allocation, card shaping and forge refs out of _mcp_shared ([a0dc6c6](https://github.com/kouroshez/coding-os/commit/a0dc6c6ef799687fc11ddffb0c4a11ca00cb28cb))
* **board_os:** split reclaim into stranded, pick, report and work-log modules ([54d08b0](https://github.com/kouroshez/coding-os/commit/54d08b0ada10a6bb755b77f74eae0af9bda9c494))
* **board_os:** split the git commit sources and the edit tool out of task history ([e0d5fef](https://github.com/kouroshez/coding-os/commit/e0d5fefc724fe5ff1abb2a9e3c63359b70d34d05))
* **board_os:** split the override audit and result types out of the gate validator ([f8112e0](https://github.com/kouroshez/coding-os/commit/f8112e0ec4aab60e2f310f783b9631d05f839651))
* **board_os:** split the ready label and reposition tools out of the lifecycle module ([1b5818b](https://github.com/kouroshez/coding-os/commit/1b5818b2859aa1261a6f37e622b2e5d2279343f5))
* **board_os:** split workflow into types, wip, deps, frontmatter, and gates ([926297d](https://github.com/kouroshez/coding-os/commit/926297dc0391a99c294a833f080fb479225b1946))
* **claude:** lift prompt, schema, env and result mapping out of dispatch ([0135441](https://github.com/kouroshez/coding-os/commit/01354419f6be6ada28011d49aa85c089e87733c3))
* **claude:** split the SDK dispatcher into options, telemetry and result modules ([9501dcd](https://github.com/kouroshez/coding-os/commit/9501dcde8268da04df2be6f6439920fac7db3f32))
* **clean-code:** move the error-handling and split-mechanics depth into references ([dc6ac4e](https://github.com/kouroshez/coding-os/commit/dc6ac4e263bf38ac9d7f077c72a4084d53774a2e))
* **cli:** move per-project skill enablement out of the skill commands ([4e9398c](https://github.com/kouroshez/coding-os/commit/4e9398c67991819183a250e008d9ec798c18395b))
* **cli:** move the first doc + graph index runs out of the init phase driver ([336b885](https://github.com/kouroshez/coding-os/commit/336b88532c381be7789205a7612bb89a83898117))
* **cli:** move the installed-asset manifest engine out of cos update ([4b29d21](https://github.com/kouroshez/coding-os/commit/4b29d21d2cea3096cbe0b4cd1d5df861f8455099))
* **cli:** split AGENTS.md, CI and Docker rendering out of renderer.py ([0acefef](https://github.com/kouroshez/coding-os/commit/0acefef5cd7a7bc613f88dcc38d0cece7e08aca7))
* **cli:** split board commands into shared, lifecycle, views, outcome and validate ([9a8dccf](https://github.com/kouroshez/coding-os/commit/9a8dccf6665e770110e365762940e94004ab19e0))
* **cli:** split doctor_extras into runtime, adapter and project checks ([b77220b](https://github.com/kouroshez/coding-os/commit/b77220bf6132548ffa88ec0f6fdc3deca77e6806))
* **cli:** split graph commands into shared, query, reindex, ingest and group modules ([cb86e0a](https://github.com/kouroshez/coding-os/commit/cb86e0a5f81ad7edbe90397dfe9e4e136a60dcb3))
* **cli:** split hub file locations and the service group out of hub_commands ([94a61e2](https://github.com/kouroshez/coding-os/commit/94a61e2e4b27111db392d549425ac89a7c0ab692))
* **cli:** split init target resolution, git bootstrap and materializers into leaves ([39f81d7](https://github.com/kouroshez/coding-os/commit/39f81d7ee171b66ebb637fc5ab0236dd71b892c7))
* **cli:** split main into path leaf, init, adopt, install and runtime command modules ([90f4b25](https://github.com/kouroshez/coding-os/commit/90f4b25060571eb2cb5ac5b776d74567e23ca3dc))
* **cli:** split the core-rule link cascade out of the module commands ([9af0a9c](https://github.com/kouroshez/coding-os/commit/9af0a9ce80e527948c13d2767c061a1364bbe437))
* **cli:** split the doctor check-orchestration sequence into a leaf ([34d7fde](https://github.com/kouroshez/coding-os/commit/34d7fdefd1aebdce264a2782a0ce66046c9a27cf))
* **cli:** split the graph doctor checks into pipeline, storage and embedding leaves ([810b763](https://github.com/kouroshez/coding-os/commit/810b7630eb4a99f742c445b97213043ffa9b1681))
* **cli:** split the runtime doctor checks into cognition, hooks, presence and schedule ([5a8f65f](https://github.com/kouroshez/coding-os/commit/5a8f65fa9f37a3d6f88103949c76ba72ff719408))
* **cli:** split the stack registry into manifest parsers and relocation rules ([d5c9b0a](https://github.com/kouroshez/coding-os/commit/d5c9b0a42850f1aa986da648c07c1ff2b0f8ade7))
* **cli:** split the stack-registry and MCP launch doctor checks into leaves ([15f78dd](https://github.com/kouroshez/coding-os/commit/15f78dda5923fe8246e2f164fca25932df778e67))
* **core:** split learning.py and graph.py along their real cohesion seams ([da130a2](https://github.com/kouroshez/coding-os/commit/da130a23beb8e9783a1923e5f11bbc39a5a7b924))
* **graph_os:** decompose cos_graph_doctor into edge, orphan and path checks ([5712ad4](https://github.com/kouroshez/coding-os/commit/5712ad4aa6b388d5b5f762977b1e4b044eccf963))
* **graph_os:** decompose the ts symbol walk into a declaration pass and a call pass ([b23a6d7](https://github.com/kouroshez/coding-os/commit/b23a6d76778ea3d521ae52ab4171839e6efab37f))
* **graph_os:** move the doctor's orphan classifier to a leaf module ([421e0ae](https://github.com/kouroshez/coding-os/commit/421e0ae5fee5ec79af8e56dfd4fed136cc36012b))
* **graph_os:** split change analysis into impact, rename and contract modules ([7dde54a](https://github.com/kouroshez/coding-os/commit/7dde54a8a68708363be09af4b0ca485eeb25f79f))
* **graph_os:** split code_generic into spec, node walk and edge-hook modules ([8299fa7](https://github.com/kouroshez/coding-os/commit/8299fa7044c2e590072583135a82850f8f73e51c))
* **graph_os:** split code_go into uid, symbol, type, package, call and regex modules ([abcf452](https://github.com/kouroshez/coding-os/commit/abcf45255c7b714a854b4905270c9be796072d72))
* **graph_os:** split code_php into a uid leaf, symbol walker, and call walker ([1bf573a](https://github.com/kouroshez/coding-os/commit/1bf573adc512b1abc9269b62ea7617dcb28d28f6))
* **graph_os:** split code_python into uid, decl, tree-sitter, visitor and emit modules ([92858a4](https://github.com/kouroshez/coding-os/commit/92858a41c860e8bccdbac0ac8b67e1d96e359f6f))
* **graph_os:** split code_ts into a uid leaf, node primitives, symbol walk and regex scanners ([ff6824e](https://github.com/kouroshez/coding-os/commit/ff6824e7582bec536982335c63430a761b0d6f3c))
* **graph_os:** split md_links into a shared base leaf, uids, resolve and section modules ([b4ff3fb](https://github.com/kouroshez/coding-os/commit/b4ff3fbdce211c3b35cb88d4ba9e33b7ffbb77a5))
* **graph_os:** split the community processes view out of the export tool ([0d366dc](https://github.com/kouroshez/coding-os/commit/0d366dce40c570190f2f8a4c7e48ad1747d89c1a))
* **graph_os:** split the contracts extractor into one module per ecosystem ([2b87fff](https://github.com/kouroshez/coding-os/commit/2b87fffc58155a7c07151b2549c7f1562077f8e6))
* **graph_os:** split the graph kernel into envelope, walk and lookup leaves ([4b83aa3](https://github.com/kouroshez/coding-os/commit/4b83aa39cd2b7ea1f507a6944d712b8299669bf4))
* **graph_os:** split the insight tools into structure, centrality, ranking and hygiene ([5a76647](https://github.com/kouroshez/coding-os/commit/5a76647fff7b93e5806ad6605316f8d2e2e4459e))
* **graph_os:** split the PHP contract scanners into their own module ([0d66cc3](https://github.com/kouroshez/coding-os/commit/0d66cc382b647ecad5a27563f6835a8c46fd16f6))
* **graph_os:** split the read tools into read, paths, references and similar ([69a41cc](https://github.com/kouroshez/coding-os/commit/69a41cca4e08ca11a03f99073a5dfebe8c1361e5))
* **graph_os:** split the reindex dispatcher into routing, state and layer modules ([349d21b](https://github.com/kouroshez/coding-os/commit/349d21b42a0411077a1897533e40faa5485cdcb6))
* **graph_os:** split the sqlite backend into a connection base and three mixins ([9346953](https://github.com/kouroshez/coding-os/commit/934695334dc9301702015aec489f50e20aa55716))
* **graph_os:** split the TypeScript regex fallback out of code_ts ([4ad773a](https://github.com/kouroshez/coding-os/commit/4ad773ad9c9c9ca257afaa1a57dbc2254d8c43af))
* **graph_os:** split uid derivation and node emission out of the shell extractor ([7681d00](https://github.com/kouroshez/coding-os/commit/7681d00dac6a5d4686eee39ebb6a9aed74d2b1e9))
* **hooks:** move doc-sync symbol extraction to its own leaf module ([e0f378f](https://github.com/kouroshez/coding-os/commit/e0f378f64dffa29286b060c53d5a6c36010b58dc))
* **hooks:** split cos-env.sh into path, log, io and state function leaves ([017772f](https://github.com/kouroshez/coding-os/commit/017772fde92c0e3204538308fe733e884dac1b28))
* **hooks:** split the branch guard into shared refs, trunk and pr policy ([384d02b](https://github.com/kouroshez/coding-os/commit/384d02bbe976aca909b6119aa230fabca2e47e49))
* **hub-ui:** clear the last three files over the backstop ([18813f1](https://github.com/kouroshez/coding-os/commit/18813f1e913c473fb94571b8be502d084d2a25e6))
* **hub-ui:** split DashboardPage into types, format leaf, data hook and widgets ([c26f5df](https://github.com/kouroshez/coding-os/commit/c26f5df4a4bb9c000f8b0ce15e5357221943f6f6))
* **hub-ui:** split DoctorPage into one module per diagnostic tab ([9dbb0b0](https://github.com/kouroshez/coding-os/commit/9dbb0b0e1d6de3bc916af518cbdbc4a3b14c1a38))
* **hub-ui:** split HubHome into types, shared leaf, icons, card and dialogs ([b0213da](https://github.com/kouroshez/coding-os/commit/b0213dad6f6966c388277c06b787e160cbf69533))
* **hub-ui:** split OnboardingWizard into types, constants, controls and a composer hook ([fc1514e](https://github.com/kouroshez/coding-os/commit/fc1514ec8c9e6059626b3f6b32b86b44c79cad42))
* **hub-ui:** split SettingsPage into types, primitives and one module per section ([1db5d42](https://github.com/kouroshez/coding-os/commit/1db5d428ce0d45284e828033ed281fe7eac85201))
* **scheduled:** split nightly into memory, board and index leg modules ([4972240](https://github.com/kouroshez/coding-os/commit/497224053b763250761b18f3ee5e6bd3a4bda756))
* **scripts:** split the MCP audit into a shared harness and per-group probes ([98bb073](https://github.com/kouroshez/coding-os/commit/98bb073e315a12bdebc57528a0593f84d71b4092))
* **supervision:** split the routing policy out of the capacity breaker ([45fd7fd](https://github.com/kouroshez/coding-os/commit/45fd7fd43967bb05a4ee8b5dfbf994af95f5790e))
* **thinking_os:** move the embedding outbox into its own module ([a6871ea](https://github.com/kouroshez/coding-os/commit/a6871ea7b0adff694b525a9164e9deceafb93816))
* **thinking_os:** split cognition into supervise, audit, routing and classify ([5f11a81](https://github.com/kouroshez/coding-os/commit/5f11a81d39a5d393bc283a688fa45b532bad1516))
* **thinking_os:** split cognition.py into dispatch, a shared leaf, and the gates ([6506f74](https://github.com/kouroshez/coding-os/commit/6506f745ba31d09cfdbb314fdf8bc72ed736e37e))
* **thinking_os:** split doc tools into hints, retrieval and header modules ([6c6fc31](https://github.com/kouroshez/coding-os/commit/6c6fc314fd83d069d3a89c2fe469750dfc415eeb))
* **thinking_os:** split doc_indexer into chunking, sources and store modules ([a1e6488](https://github.com/kouroshez/coding-os/commit/a1e64889b856e4dbe549152d9c497be88bd70bf0))
* **thinking_os:** split formula dispatch into request building and persistence ([cbf7fd4](https://github.com/kouroshez/coding-os/commit/cbf7fd4c47d64f8b8803f6c0e0093621c9906f2f))
* **thinking_os:** split learning into extract, suggest, validate and generalize modules ([789c734](https://github.com/kouroshez/coding-os/commit/789c734b416ab019bb1480f8cb7f15fc06b6252e))
* **thinking_os:** split memory tools into ranking, semantic and search modules ([5452fba](https://github.com/kouroshez/coding-os/commit/5452fba25c2ebb037fa1a9eb6175aaa760f7245d))
* **thinking_os:** split skill routing, weights and failure anatomy out of routing.py ([021b7de](https://github.com/kouroshez/coding-os/commit/021b7de8ea133dab523467837816f1a1629e6426))
* **thinking_os:** split the agent and situation registry loaders out of cognition ([9ed4c36](https://github.com/kouroshez/coding-os/commit/9ed4c369e0652394dad6d6b17039824f11825c11))
* **thinking_os:** split the cognitive artifact value types out of the schemas module ([0ef8ce4](https://github.com/kouroshez/coding-os/commit/0ef8ce41b94fec6491430b068f0750ccd180643f))
* **thinking_os:** split the cos_task_* tools into records and lifecycle modules ([3169a07](https://github.com/kouroshez/coding-os/commit/3169a07b1078a1be8fc82431281a377553dc3e65))
* **thinking_os:** split the human-readable report renderer out of health_check ([27bd214](https://github.com/kouroshez/coding-os/commit/27bd21424186e6aff0eaa6e0bd7ac81cc7a60581))
* **thinking_os:** split the MCP envelope into size, trim, subgraph, errors, and gating ([d11b6ce](https://github.com/kouroshez/coding-os/commit/d11b6ceae5eb529436ef5c37468ac16ae0d72b71))
* **thinking_os:** split the metric, recall and learning tools out of _tools_memory ([08b2780](https://github.com/kouroshez/coding-os/commit/08b2780fc3b4175f5ea35aba8b56414886af0f21))
* **thinking_os:** split the prompt keyword heuristics out of the formula composer ([c4234fb](https://github.com/kouroshez/coding-os/commit/c4234fb1911149168f41a41c60b242a9ab20abc2))
* **web:** move the cognition router to a leaf and split out the dispatch views ([e8c9169](https://github.com/kouroshez/coding-os/commit/e8c9169df4467b43fb253f812087710142fc4a88))
* **web:** split board routes into shared, presence, autospawn, git and view modules ([11721b0](https://github.com/kouroshez/coding-os/commit/11721b0e89c285c05be715541ccc594aecd1eb77))
* **web:** split cognition chat serialization into a leaf module ([080cca3](https://github.com/kouroshez/coding-os/commit/080cca39eb381644cd9fe59d825b705045cf97f2))
* **web:** split hub routes into shared, init, init-routes and scan ([7dad131](https://github.com/kouroshez/coding-os/commit/7dad131e998113568440eebf5098d393e9d28c05))
* **web:** split presence runtime readers and context accounting into leaves ([8141db5](https://github.com/kouroshez/coding-os/commit/8141db55256d606d882cc6b3d462a7dc04621dc9))
* **web:** split the cached graph export endpoint off the thin route wrappers ([2da5a2d](https://github.com/kouroshez/coding-os/commit/2da5a2d8e0a545d1d708d4f26ba0b0bbf37c3e5b))
* **web:** split the cognition chat routes from their SDK, prompt and lookup seams ([825389c](https://github.com/kouroshez/coding-os/commit/825389c777d2ead7b0e0990cfd3fe4640715c180))
* **web:** split the cognition routes into chat and onboarding modules ([a2c2957](https://github.com/kouroshez/coding-os/commit/a2c29577b998cd7eba93a2b4e4eacf2eb3d2dbdf))
* **web:** split the config routes into shared, read and mutation modules ([a283be8](https://github.com/kouroshez/coding-os/commit/a283be807de4460bd42468e06aa8a76093bfd581))
* **web:** split the presence and activity snapshots out of the SSE stream route ([d413170](https://github.com/kouroshez/coding-os/commit/d4131700ec1d5f495dc98de36b0dbfcb4e52abae))


### Documentation

* **adr-0016:** record the held-out eval-gate spike verdict as a measured no-go ([b9326b0](https://github.com/kouroshez/coding-os/commit/b9326b0ee84f1ddaca3fae45992a52c6c9d4c709))
* **ci-gates:** record the four burndown splits and the two traps they surfaced ([fbb77e5](https://github.com/kouroshez/coding-os/commit/fbb77e5a4eb663da2af5a74e85ed7b8871da7bb0))
* **ci-gates:** record why embeddings.py stays whole and how the envelope split cleared mypy ([bf34bad](https://github.com/kouroshez/coding-os/commit/bf34bad901d9d0a05f98fbb542b652ae13d26e2f))
* **ci:** record why the pr_commands split was reverted ([b2c8f70](https://github.com/kouroshez/coding-os/commit/b2c8f70b4ae5bcc144489abac38e9298f6a30eba))
* **clean-code:** adopt one output contract for scripts and checks ([99d6000](https://github.com/kouroshez/coding-os/commit/99d600055155cf9e23573507f97d2a2621ea9f68))
* **clean-code:** name resource lifetime on the failing path as a rule ([d26fd8f](https://github.com/kouroshez/coding-os/commit/d26fd8f3b7d4cccd40524cd9a09b9936d6143d91))
* **clean-code:** record the five resolution mechanisms a module split breaks ([e768e4b](https://github.com/kouroshez/coding-os/commit/e768e4bbcc701680d3a1197f892c1e46c08da88c))
* **insights:** record the reproduce-before-fixing lesson from TASK-929 ([319f681](https://github.com/kouroshez/coding-os/commit/319f681098deea599c669f2a9e10447bc3dc17c7))
* **insights:** record the type-checker re-export trap in a facade split ([5e27b56](https://github.com/kouroshez/coding-os/commit/5e27b56e480404ff44cf8ac291912192f11216d2))
* **readme:** merge the two quickstarts and correct the supervision copy ([b11a987](https://github.com/kouroshez/coding-os/commit/b11a987ad94c46e22a416ff5bc1fc210403c4cd7))
* record the real oversized-file state after the burndown session ([cb0f23b](https://github.com/kouroshez/coding-os/commit/cb0f23b05740607ac3a0369627ef9a720e258df4))
* record the session-context exception and the real burndown numbers ([b8b30e2](https://github.com/kouroshez/coding-os/commit/b8b30e29302908d94acb5fde77d58965a39fb503))
* **skills:** add upload, rate-limit, concurrency, CQS and file-splitting standards ([51d48c1](https://github.com/kouroshez/coding-os/commit/51d48c177eff65fd75a64e87e4fbdd3c4018763c))


### Build

* **deps:** bump pydantic-settings from 2.14.1 to 2.14.2 ([#25](https://github.com/kouroshez/coding-os/issues/25)) ([b972718](https://github.com/kouroshez/coding-os/commit/b9727185d238411ccfee102045f5e68f3ca8e0fe))

## [0.3.12](https://github.com/kouroshez/coding-os/compare/v0.3.11...v0.3.12) (2026-08-10)


### Added

* **quality:** enforce an 800-line file ceiling at write time and in consumers ([859425a](https://github.com/kouroshez/coding-os/commit/859425a4d8ed0bdd47ff27ae059adeb8944bf59e))
* **quality:** make the file-size budget cohesion-first and surface it everywhere ([541b643](https://github.com/kouroshez/coding-os/commit/541b6439a7ae895bc1f18522188067ecf87b53a8))


### Fixed

* **ci:** give diff-cover a real merge base so the gate can pass ([20248dd](https://github.com/kouroshez/coding-os/commit/20248ddef45aa61c2c8cf6438b2bd7ee71f29b9d))
* **ci:** reformat after the main.py split and tighten the size ratchet ([3602dce](https://github.com/kouroshez/coding-os/commit/3602dcef542877cebef7912be261befb5dcab91e))
* **ci:** stop counting unresolvable flat sibling imports in the mypy ratchet ([93a09ab](https://github.com/kouroshez/coding-os/commit/93a09ab8feeb6280b21c16c5bea3c2a25065c4c0))
* **thinking_os:** make the database sibling imports work under both import identities ([e257310](https://github.com/kouroshez/coding-os/commit/e257310ed1607b412f6e954f9f6314001194f146))


### Changed

* **cli:** split main.py into cohesive init modules, 3111 lines to 1605 ([3f1cabc](https://github.com/kouroshez/coding-os/commit/3f1cabc17512a61058060c333a9465b32aac466d))
* **thinking_os:** split database.py into paths, the migration ledger, and a facade ([70f3533](https://github.com/kouroshez/coding-os/commit/70f3533f59223e7a521023770afed5475d67719e))
* **thinking_os:** split the 3159-line server.py into a facade plus domain modules ([4d12c4d](https://github.com/kouroshez/coding-os/commit/4d12c4deeb7b05f24ba491a1ec13d0617907e1f2))


### Documentation

* **insights:** record the four break modes of a dual-identity module split ([7414348](https://github.com/kouroshez/coding-os/commit/7414348a462775380e2ac946153281b133b02c3d))


### Build

* **deps:** bump aiohttp from 3.13.5 to 3.14.3 ([#29](https://github.com/kouroshez/coding-os/issues/29)) ([e96e7cf](https://github.com/kouroshez/coding-os/commit/e96e7cf596e3a329b2a91c7089c297f2063e76c1))
* **deps:** bump cryptography from 48.0.0 to 50.0.0 ([#26](https://github.com/kouroshez/coding-os/issues/26)) ([0f70fed](https://github.com/kouroshez/coding-os/commit/0f70fed7169283b10f5202aa087950058baefe4d))
* **deps:** bump mcp from 1.27.2 to 1.28.1 ([#27](https://github.com/kouroshez/coding-os/issues/27)) ([ea27f11](https://github.com/kouroshez/coding-os/commit/ea27f11ea7cfa5d4db2276883ba63fe61fd2a447))
* **deps:** bump python-multipart from 0.0.29 to 0.0.31 ([#51](https://github.com/kouroshez/coding-os/issues/51)) ([64296e1](https://github.com/kouroshez/coding-os/commit/64296e100b1a78e5efb1145bc4a58842aebc0977))
* **deps:** bump starlette from 1.2.1 to 1.3.1 ([#50](https://github.com/kouroshez/coding-os/issues/50)) ([86e2a15](https://github.com/kouroshez/coding-os/commit/86e2a15d289dc24d898ddc4906bcf56ba4e145a1))
* **deps:** bump torch from 2.12.0 to 2.13.0 ([#28](https://github.com/kouroshez/coding-os/issues/28)) ([de6cc90](https://github.com/kouroshez/coding-os/commit/de6cc900490f99c4f9411288d86c2ecd9ae7cdcf))

## [0.3.11](https://github.com/kouroshez/coding-os/compare/v0.3.10...v0.3.11) (2026-08-10)


### Fixed

* **ci:** keep sigstore bundles out of the PyPI upload directory ([5080d3c](https://github.com/kouroshez/coding-os/commit/5080d3c90b9a3ee13328773a84a4e365e3f52c0e))
* **ci:** write the release SBOM to an existing directory ([3461b46](https://github.com/kouroshez/coding-os/commit/3461b46a0512b2e869a082b2670c5116ceef8001))

## [0.3.10](https://github.com/kouroshez/coding-os/compare/v0.3.9...v0.3.10) (2026-08-09)


### Added

* **board:** add cos task-validate --repair for stale duplicate frontmatter ([d609a32](https://github.com/kouroshez/coding-os/commit/d609a32b174aefeaa816930154a94b0fecba04c4))
* **graph_os:** reproducible third-party token-cost benchmark harness ([ba8d79c](https://github.com/kouroshez/coding-os/commit/ba8d79c65f368bedd2d302ba69bf49f34074d6cb))


### Fixed

* **cli:** stop cos init rejecting piped stdin for the agent prompt ([e1b4a86](https://github.com/kouroshez/coding-os/commit/e1b4a86f7878f2da76dddd4850bd6ec63f922e8c))
* **cli:** stop cos update reporting drift on a freshly initialised project ([6e0a95f](https://github.com/kouroshez/coding-os/commit/6e0a95fa2bd9cefcd2b5656303c745a0f5a02a06))
* **lint:** clear the ruff baseline and fix bug-prone patterns ([7caea1e](https://github.com/kouroshez/coding-os/commit/7caea1ed35f974ba091a17cf2c012d0a1a51eb9a))
* **tests:** type the frontmatter-repair tests and use the core.board_os import path ([d20bcbc](https://github.com/kouroshez/coding-os/commit/d20bcbc7666a07bd37e954e8cff0f0e02a942411))
* **types:** declare __all__ on the split facades so re-exports are explicit for mypy ([2c6fdac](https://github.com/kouroshez/coding-os/commit/2c6fdac48106d74dfd6b9303ecd5ad7c4523df53))


### Changed

* **board_os:** split mcp_tools.py into a facade over private _mcp_* siblings ([6f0e9fc](https://github.com/kouroshez/coding-os/commit/6f0e9fc4f78ec84ed0a211641aadade4287639c3))
* **cli:** split doctor.py into a facade over doctor_checks_* siblings ([2ec606b](https://github.com/kouroshez/coding-os/commit/2ec606b4004486da3c27b1efb7db15287d3c8b30))
* **graph_os:** split graph.py into four private tool-family modules ([8478d64](https://github.com/kouroshez/coding-os/commit/8478d6408108d8838e78d284fde7a4181377c241))
* **tests:** split test_cli.py into _cli_suite part modules ([141e102](https://github.com/kouroshez/coding-os/commit/141e1029ec6977c022347e0ad56d9b436a814542))


### Documentation

* add front-matter headers to ci-gates and stability-contract ([b19fcf1](https://github.com/kouroshez/coding-os/commit/b19fcf1a87dd1c82151b08aaf93d108edca58079))
* correct the mypy baseline and state each gate's real scope ([863c5b4](https://github.com/kouroshez/coding-os/commit/863c5b44ecb0753bbbbe60a1b374eb184d914034))
* **governance:** add GOVERNANCE + MAINTAINERS and the agent-workflow contributor guide ([4915a67](https://github.com/kouroshez/coding-os/commit/4915a67172dd5cffabad1585c01e727cc4b442e7))
* **readme:** correct the supervision cooldown scope and list the command ([299c4f0](https://github.com/kouroshez/coding-os/commit/299c4f033f0263212ad9c137f7305ed970490fff))
* refresh generated indexes for ci-gates and stability-contract ([6bd0391](https://github.com/kouroshez/coding-os/commit/6bd0391662e7dde5dbba693a9e4eb2b1c17ced10))


### Build

* **coverage:** scope the coverage gate to src/core on the src suites ([f7a7dec](https://github.com/kouroshez/coding-os/commit/f7a7dec6dd4eff5e6230935de064802298d8ac62))

## [0.3.9](https://github.com/kouroshez/coding-os/compare/v0.3.8...v0.3.9) (2026-08-07)


### Fixed

* **board:** anchor the DoD verify ledger to the project root ([1a04d6e](https://github.com/kouroshez/coding-os/commit/1a04d6ee629c038ce34788962a2d119a09dcb534))
* **cli:** stop cos update deleting adapter-owned hooks ([54dac1d](https://github.com/kouroshez/coding-os/commit/54dac1d7cafcc4e3da36f44ec43b74efa439ffd5))
* **hub:** keep a saved supervision target visible when its adapter is unavailable ([9d54c91](https://github.com/kouroshez/coding-os/commit/9d54c91db3cc0bb8b7f595bd0036053cb8fd9163))
* **hub:** stop the settings toggle reading inverted ([5966767](https://github.com/kouroshez/coding-os/commit/5966767657b86192d0248b7e687841e19aaf661a))
* **supervision:** enforce trigger modes and make the orchestrator target the role default ([f221330](https://github.com/kouroshez/coding-os/commit/f2213309825fcc2ccb02aad11e034ef9b542b26a))
* **supervision:** hold the recovery probe for its whole run and report the soonest recovery ([44cfb37](https://github.com/kouroshez/coding-os/commit/44cfb37d2a69193740b875c89dd0fc6346fdd015))
* **supervision:** meter capacity per model pool instead of per adapter ([bfe13e6](https://github.com/kouroshez/coding-os/commit/bfe13e6e0b084ba0df917c619f4bbcd5ff2624b0))
* **supervision:** restore adapter validation and protect the capacity recovery probe ([8451079](https://github.com/kouroshez/coding-os/commit/84510794d60b6a4d77b2b651dfdfac5051aa2b0a))


### Documentation

* refresh the engineering index after the supervision doc update ([501687f](https://github.com/kouroshez/coding-os/commit/501687f91c092339fd9dd5729f808b546a44723c))
* **rules:** sync the model-routing rule to the enforced supervision trigger modes ([96cefa4](https://github.com/kouroshez/coding-os/commit/96cefa429057e033d7257038e5092b7eb7455c29))
* **supervision:** document probe-lease duration, fleet exhaustion, and the adapter contract ([05ee39c](https://github.com/kouroshez/coding-os/commit/05ee39c3c92e79e286808049ddd35c24eb659800))
* **supervision:** document the enforced contract, add the operator playbook and README section ([b1d0633](https://github.com/kouroshez/coding-os/commit/b1d06334da87b4c51f3eb98155587d3557dfe96f))
* **supervision:** record what a provider limit actually applies to ([72c8c2b](https://github.com/kouroshez/coding-os/commit/72c8c2bfbf609d0cf26c8db80d144ebe1405907a))

## [0.3.8](https://github.com/kouroshez/coding-os/compare/v0.3.7...v0.3.8) (2026-08-07)


### Fixed

* make supervision configurable without Hub ([33001c0](https://github.com/kouroshez/coding-os/commit/33001c04397843281c0422dc124a99d477e7341e))
* sync shared supervision OpenAPI schema ([29e2509](https://github.com/kouroshez/coding-os/commit/29e2509adef06a165705bcf463e13af52b12166a))

## [0.3.7](https://github.com/kouroshez/coding-os/compare/v0.3.6...v0.3.7) (2026-08-07)


### Added

* add configurable agent supervision ([b924120](https://github.com/kouroshez/coding-os/commit/b92412003248b2acc4421b7828d950af4ffe91f1))


### Fixed

* sync Hub OpenAPI snapshot ([bdbe6be](https://github.com/kouroshez/coding-os/commit/bdbe6be8ae3aca22f86bfbba427a4fd150aaf874))


### Documentation

* define configurable agent supervision ([bc5846f](https://github.com/kouroshez/coding-os/commit/bc5846ffcf2c91991488ba972242b086de791c0e))

## [0.3.6](https://github.com/kouroshez/coding-os/compare/v0.3.5...v0.3.6) (2026-08-06)


### Fixed

* **ci:** refresh golden fixtures and scaffold manifest for the CLAUDE.md entrypoint ([4251243](https://github.com/kouroshez/coding-os/commit/4251243bb2a10ef3378645da5856261a9997c27e))
* **cli:** emit Node 22 in generated CI and the TypeScript Dockerfile ([cceba34](https://github.com/kouroshez/coding-os/commit/cceba345005e627e181550de7b64ef873e0ed357))
* **release:** keep the PyPI recovery hatch reachable and pin checkout to the release sha ([ce2d180](https://github.com/kouroshez/coding-os/commit/ce2d180a0d6c2b93887321bc4be9ac67f2b28fbc))

## [0.3.5](https://github.com/kouroshez/coding-os/compare/v0.3.4...v0.3.5) (2026-08-06)


### Fixed

* **templates:** raise the go-fiber dependency floors past 21 advisories ([1a30a05](https://github.com/kouroshez/coding-os/commit/1a30a0583a001b60f5c440e86500c5ca92b4cf6e))
* **cli:** create each adapter's root entrypoint symlink during init and update ([beceeaa](https://github.com/kouroshez/coding-os/commit/beceeaa691786b6726a15bd1fe125583eb92e8ce))

### Documentation

* **readme:** point the version badge at PyPI instead of GitHub releases ([f7376f3](https://github.com/kouroshez/coding-os/commit/f7376f3c1c91681207a87bf4faeb523a96c32458))
* **readme:** drop the per-project token figures from the scoping section ([2ab0420](https://github.com/kouroshez/coding-os/commit/2ab0420521bda92521d7371ae285af1e2a067e17))
* **readme:** state skill scoping accurately with measured numbers ([57f2cd0](https://github.com/kouroshez/coding-os/commit/57f2cd01f62b444fe7eb3bebbfe9b4d87ab886f0))
* drop residual references to removed third-party material ([70788bb](https://github.com/kouroshez/coding-os/commit/70788bb9ab2244167a8cd6d3d249dc1924665d70))
* translate all remaining non-English prose to English ([f26ff1d](https://github.com/kouroshez/coding-os/commit/f26ff1d0861e830b634518cd9e640e40a541bdc4))
* **readme:** lead with measured context economics + a visible support surface ([e265f88](https://github.com/kouroshez/coding-os/commit/e265f88ea365d213b1927a34e480c44a0640abaa))

### Build

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
