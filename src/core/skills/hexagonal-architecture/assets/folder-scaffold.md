# Folder Scaffold — Copy-Pastable Skeletons

Three minimal scaffolds you can drop into a fresh repo and start writing business logic immediately. Each leaves the framework choices opinionated to match this project's stack.

## Go + Fiber Skeleton

```bash
mkdir -p backend/{cmd/api,internal/{domain,app/{ports,usecase},adapter/{http,postgres,system,fakes}},pkg/apperr}

# Touch placeholder files so go vet runs cleanly
cat > backend/go.mod << 'EOF'
module backend

go 1.23
EOF

cat > backend/cmd/api/main.go << 'EOF'
package main

func main() {
    // TODO: wire outbound adapters, build use cases, mount Fiber app, listen.
}
EOF

cat > backend/internal/domain/.keep << 'EOF'
# Domain layer — pure Go, no framework imports.
# Each bounded context gets a subfolder.
EOF

cat > backend/internal/app/ports/.keep << 'EOF'
# Outbound port interfaces. Owned by the application layer.
# Adapters under internal/adapter/ implement these.
EOF

cat > backend/internal/app/usecase/.keep << 'EOF'
# One file per use case. Each has a single Execute method
# that takes a typed Input and returns a typed Output.
EOF

cat > backend/internal/adapter/.keep << 'EOF'
# Outer ring. http/ for inbound (Fiber), postgres/ stripe/ etc. for outbound.
EOF

cat > backend/.golangci.yml << 'EOF'
linters:
  enable:
    - depguard

linters-settings:
  depguard:
    rules:
      domain-pure:
        files: ["**/internal/domain/**"]
        deny:
          - pkg: "github.com/gofiber/**"
            desc: "domain must not import http frameworks"
          - pkg: "github.com/jackc/pgx/**"
            desc: "domain must not import database drivers"
EOF
```

## Python + FastAPI Skeleton

```bash
mkdir -p ai-adapter/src/ai_adapter/{domain,application/{ports,usecase},infrastructure/{postgres,llm,system},delivery/{http/routers,cli},fakes}
mkdir -p ai-adapter/tests/integration

cd ai-adapter

cat > pyproject.toml << 'EOF'
[project]
name = "ai-adapter"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "asyncpg>=0.30",
  "pydantic>=2.10",
  "anthropic>=0.40",  # or openai, swap based on provider
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "import-linter>=2"]
EOF

cat > .importlinter << 'EOF'
[importlinter]
root_packages = [ai_adapter]

[importlinter:contract:1]
name = "Domain has no infrastructure imports"
type = forbidden
source_modules = [ai_adapter.domain]
forbidden_modules = [
    ai_adapter.application,
    ai_adapter.infrastructure,
    ai_adapter.delivery,
    fastapi,
    asyncpg,
    anthropic,
]

[importlinter:contract:2]
name = "Application has no infrastructure or delivery imports"
type = forbidden
source_modules = [ai_adapter.application]
forbidden_modules = [
    ai_adapter.infrastructure,
    ai_adapter.delivery,
    fastapi,
    asyncpg,
]
EOF

# Empty __init__.py everywhere so imports work
find src -type d -exec touch {}/__init__.py \;

cat > src/ai_adapter/delivery/http/server.py << 'EOF'
"""FastAPI app factory. Wires use cases via lifespan."""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # TODO: build outbound adapters, instantiate use cases, attach to app.state
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    # TODO: include_router(...)
    return app
EOF
```

Run `lint-imports` to catch reverse dependencies in CI.

## React Native Skeleton

```bash
mkdir -p mobile/src/{domain/{primitives,lesson,user},application/{ports,usecase},infrastructure/{http,storage,analytics,system},delivery/{navigation,providers,screens,components},fakes}

cd mobile

cat > tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "jsx": "react-native",
    "baseUrl": "./src",
    "paths": {
      "@domain/*":         ["domain/*"],
      "@application/*":    ["application/*"],
      "@infrastructure/*": ["infrastructure/*"],
      "@delivery/*":       ["delivery/*"],
      "@fakes/*":          ["fakes/*"]
    }
  }
}
EOF

cat > .eslintrc.cjs << 'EOF'
// Boundary enforcement — prevent reverse dependencies.
module.exports = {
  plugins: ['boundaries'],
  settings: {
    'boundaries/elements': [
      { type: 'domain',         pattern: 'src/domain/*' },
      { type: 'application',    pattern: 'src/application/*' },
      { type: 'infrastructure', pattern: 'src/infrastructure/*' },
      { type: 'delivery',       pattern: 'src/delivery/*' },
      { type: 'fakes',          pattern: 'src/fakes/*' },
    ],
  },
  rules: {
    'boundaries/element-types': ['error', {
      default: 'disallow',
      rules: [
        { from: 'domain',         allow: ['domain'] },
        { from: 'application',    allow: ['domain', 'application'] },
        { from: 'infrastructure', allow: ['domain', 'application', 'infrastructure'] },
        { from: 'delivery',       allow: ['domain', 'application', 'delivery'] },
        { from: 'fakes',          allow: ['domain', 'application', 'fakes'] },
      ],
    }],
  },
};
EOF

cat > src/delivery/providers/DependencyProvider.tsx << 'EOF'
import { createContext, useContext, type PropsWithChildren } from 'react';

export interface UseCases {
  // TODO: list each use case as a typed property
}

const Ctx = createContext<UseCases | null>(null);

export function DependencyProvider({
  value, children,
}: PropsWithChildren<{ value: UseCases }>) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUseCase<K extends keyof UseCases>(key: K): UseCases[K] {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useUseCase must be used inside <DependencyProvider>');
  return ctx[key];
}
EOF
```

Install `eslint-plugin-boundaries` for the boundary rule above.

## After Scaffolding — First Steps

1. **Pick one use case** that genuinely matters (e.g., `RegisterUser`).
2. Write the **domain entity first** (with its invariants) and its tests.
3. Write the **use case** with fake outbound ports + tests.
4. Write the **real adapters** last (Postgres, HTTP route, etc).
5. Wire into composition root.
6. Smoke test end-to-end.

This sequence catches design mistakes at the cheapest moment — domain unit tests fail in milliseconds, integration tests take seconds, e2e takes minutes.
