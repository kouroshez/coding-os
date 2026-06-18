# Skill Enforcement

Auto-generated. Before writing code matching any glob below,
invoke the matching skill via the `Skill` tool.

| Globs | Primary Skill | Secondary Skills | Stack |
| --- | --- | --- | --- |
| `src/frontend/**/*.ts` | `angular` | clean-code, frontend-fundamentals, a11y, state-management, testing-strategy, performance | angular |
| `src/frontend/**/*.component.ts` | `angular` | clean-code, frontend-fundamentals, a11y | angular |
| `src/frontend/**/*.service.ts` | `angular` | state-management, clean-code, frontend-fundamentals | angular |
| `src/backend/**/*.cs` | `aspnet-core` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | aspnet-core |
| `src/backend/**/*Service.cs`, `src/backend/**/Repositories/**/*.cs`, `src/backend/**/Data/**/*.cs` | `aspnet-core` | clean-code, db-design, backend-fundamentals | aspnet-core |
| `src/backend/**/*Authorization*.cs`, `src/backend/**/Auth*.cs` | `aspnet-core` | auth-patterns, security-web, clean-code | aspnet-core |
| `src/frontend/**/*.{ts,astro}` | `astro` | clean-code, frontend-design, frontend-fundamentals, a11y, performance, testing-strategy | astro |
| `src/frontend/**/components/**/*.astro`, `src/frontend/**/pages/**/*.astro` | `astro` | clean-code, frontend-design, frontend-fundamentals, a11y | astro |
| `src/frontend/**/content/**/*.ts`, `src/frontend/**/pages/api/**/*.ts` | `astro` | clean-code, frontend-fundamentals, api-design | astro |
| `src/backend/**/*.py` | `python-django` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | django |
| `src/backend/**/models.py`, `src/backend/**/migrations/*.py` | `python-django` | clean-code, db-design, backend-fundamentals | django |
| `src/backend/**/auth*.py`, `src/backend/**/permissions.py` | `python-django` | auth-patterns, security-web, clean-code | django |
| `src/backend/**/*.py` | `python-fastapi` | clean-code, api-design, backend-fundamentals, hexagonal-architecture, auth-patterns, security-web, testing-strategy, observability | fastapi |
| `src/backend/**/models.py`, `src/backend/**/db/**/*.py`, `src/backend/**/migrations/**/*.py` | `python-fastapi` | clean-code, db-design, backend-fundamentals | fastapi |
| `src/backend/**/auth*.py`, `src/backend/**/security.py` | `python-fastapi` | auth-patterns, security-web, clean-code | fastapi |
| `src/mobile/**/*.dart` | `flutter` | clean-code, frontend-fundamentals, mobile-fundamentals, a11y | flutter |
| `src/mobile/**/screens/**/*.dart`, `src/mobile/**/widgets/**/*.dart` | `flutter` | clean-code, state-management, performance | flutter |
| `src/mobile/**/state/**/*.dart` | `flutter` | state-management, clean-code | flutter |
| `src/backend/**/*.go` | `go-patterns` | clean-code, backend-fundamentals, api-design, hexagonal-architecture, testing-strategy, observability | go |
| `src/backend/**/db/**/*.go`, `src/backend/**/repository/**/*.go` | `go-patterns` | clean-code, db-design, backend-fundamentals | go |
| `src/backend/**/*.go` | `go-fiber` | clean-code, backend-fundamentals, api-design, hexagonal-architecture, auth-patterns, security-web, testing-strategy, observability | go-fiber |
| `src/backend/**/db/**/*.go`, `src/backend/**/migrations/**/*.go`, `src/backend/**/repository/**/*.go` | `go-fiber` | clean-code, db-design, backend-fundamentals | go-fiber |
| `src/backend/**/auth*.go`, `src/backend/**/middleware/auth*.go` | `go-fiber` | auth-patterns, security-web, clean-code | go-fiber |
| `src/backend/**/*.php` | `laravel` | php, clean-code, backend-fundamentals, api-design, security-web, testing-strategy | laravel |
| `src/backend/**/Models/**/*.php`, `src/backend/**/database/**/*.php` | `laravel` | php, clean-code, db-design | laravel |
| `src/backend/**/Middleware/**/*.php`, `src/backend/**/auth*.php` | `laravel` | php, security-web, clean-code | laravel |
| `src/core/thinking_os/**/*.py` | `python-meta-server` | graph-explorer, clean-code, thinking_os, mcp-tool-authoring, llm-patterns, observability, agent-memory | meta |
| `src/core/thinking_os/tools/memory.py`, `src/core/thinking_os/tools/learning.py`, `src/core/thinking_os/tools/retrieve.py` | `agent-memory` | python-meta-server, mcp-tool-authoring, clean-code | meta |
| `src/core/thinking_os/tools/*.py`, `src/core/graph_os/tools/*.py`, `src/core/board_os/mcp_tools.py`, `src/core/web/routes/*.py` | `mcp-tool-authoring` | python-meta-server, graph-explorer, clean-code | meta |
| `src/core/graph_os/**/*.py` | `graph-os-authoring` | python-meta-server, graph-explorer, clean-code | meta |
| `src/core/board_os/**/*.py` | `python-meta-server` | graph-explorer, clean-code, task-driver | meta |
| `src/cli/**/*.py` | `python-meta-server` | graph-explorer, clean-code, testing-strategy | meta |
| `src/core/web/**/*.py` | `python-meta-server` | graph-explorer, clean-code, api-design, observability | meta |
| `src/core/web/ui/**/*.{ts,tsx}` | `react-vite-hub` | clean-code, frontend-fundamentals, a11y, state-management | meta |
| `src/adapters/claude/**/*.py` | `claude-sdk-integration` | graph-explorer, clean-code, llm-patterns, observability | meta |
| `src/adapters/codex/**/*.py` | `graph-explorer` | clean-code, thinking_os | meta |
| `src/core/hooks/*.sh` | `hook-authoring` | meta-engineering, clean-code, thinking_os | meta |
| `src/core/hooks/_helpers/*.py` | `hook-authoring` | meta-engineering, clean-code, thinking_os | meta |
| `src/templates/**/stack.yaml` | `meta-engineering` | thinking_os, clean-code | meta |
| `src/core/hooks/registry.yaml` | `hook-authoring` | meta-engineering, thinking_os, clean-code | meta |
| `docs/tasks/TASK-*.md` | `task-driver` | thinking_os | meta |
| `.github/workflows/*.yml`, `Dockerfile`, `docker-compose*.yml` | `deployment-cicd` | clean-code, observability | meta |
| `src/backend/**/*.ts` | `nestjs` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | nestjs |
| `src/backend/**/*.service.ts`, `src/backend/**/repositories/**/*.ts`, `src/backend/**/db/**/*.ts` | `nestjs` | clean-code, db-design, backend-fundamentals | nestjs |
| `src/backend/**/*.guard.ts`, `src/backend/**/auth*.ts` | `nestjs` | auth-patterns, security-web, clean-code | nestjs |
| `src/frontend/**/*.{ts,tsx}` | `nextjs-react` | clean-code, frontend-design, frontend-fundamentals, a11y, performance, testing-strategy | nextjs |
| `src/frontend/**/components/**/*.{ts,tsx}`, `src/frontend/**/app/**/page.tsx`, `src/frontend/**/app/**/layout.tsx` | `nextjs-react` | clean-code, frontend-design, frontend-fundamentals, a11y | nextjs |
| `src/frontend/**/store/**/*.ts`, `src/frontend/**/stores/**/*.ts`, `src/frontend/**/hooks/use*.ts` | `nextjs-react` | state-management, clean-code, frontend-fundamentals | nextjs |
| `src/backend/**/*.ts` | `node-express` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | node-express |
| `src/backend/**/repositories/**/*.ts`, `src/backend/**/db/**/*.ts` | `node-express` | clean-code, db-design, backend-fundamentals | node-express |
| `src/backend/**/middleware/auth*.ts`, `src/backend/**/auth*.ts` | `node-express` | auth-patterns, security-web, clean-code | node-express |
| `src/backend/**/*.rb` | `rails` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | rails |
| `src/backend/**/models/**/*.rb`, `src/backend/**/migrate/**/*.rb` | `rails` | clean-code, db-design, backend-fundamentals | rails |
| `src/backend/**/controllers/concerns/auth*.rb`, `src/backend/**/models/concerns/auth*.rb` | `rails` | auth-patterns, security-web, clean-code | rails |
| `src/mobile/**/*.{ts,tsx}` | `react-native-mobile` | clean-code, frontend-fundamentals, mobile-fundamentals, a11y | react-native |
| `src/mobile/**/components/**/*.{ts,tsx}`, `src/mobile/**/screens/**/*.{ts,tsx}` | `react-native-patterns` | clean-code, react-native-mobile, state-management, performance | react-native |
| `src/backend/**/*.rs` | `rust` | clean-code, backend-fundamentals, api-design, hexagonal-architecture, testing-strategy, observability | rust-axum |
| `src/backend/**/routes/**/*.rs`, `src/backend/**/handlers/**/*.rs` | `rust` | clean-code, api-design, backend-fundamentals | rust-axum |
| `src/backend/**/auth*.rs`, `src/backend/**/middleware/**/*.rs` | `rust` | auth-patterns, security-web, clean-code | rust-axum |
| `src/backend/**/*.java` | `spring-boot` | clean-code, backend-fundamentals, api-design, auth-patterns, security-web, testing-strategy, observability | spring-boot |
| `src/backend/**/*Repository.java`, `src/backend/**/repository/**/*.java`, `src/backend/**/*Entity.java` | `spring-boot` | clean-code, db-design, backend-fundamentals | spring-boot |
| `src/backend/**/*SecurityConfig.java`, `src/backend/**/security/**/*.java`, `src/backend/**/Auth*.java` | `spring-boot` | auth-patterns, security-web, clean-code | spring-boot |
| `src/frontend/**/*.{svelte,ts}` | `svelte` | clean-code, frontend-fundamentals, frontend-design, a11y, performance, testing-strategy | svelte-sveltekit |
| `src/frontend/**/lib/stores/**/*.ts`, `src/frontend/**/stores/**/*.ts` | `svelte` | state-management, clean-code, frontend-fundamentals | svelte-sveltekit |
| `src/frontend/**/*.{vue,ts}` | `vue-nuxt` | clean-code, frontend-fundamentals, frontend-design, a11y, performance, testing-strategy | vue-nuxt |
| `src/frontend/**/composables/**/*.ts`, `src/frontend/**/stores/**/*.ts` | `vue-nuxt` | state-management, clean-code, frontend-fundamentals | vue-nuxt |
| `src/backend/**/*.php` | `wordpress` | php, clean-code, security-web | wordpress |
| `src/backend/plugin/**/*.php` | `wordpress` | php, clean-code, security-web, api-design | wordpress |
