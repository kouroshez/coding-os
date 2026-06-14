---
name: rails
tier: stack
domain: [backend]
description: Use when creating or modifying Ruby files under src/backend/ in a Ruby on Rails service — controllers, ActiveRecord models, routes.rb, concerns, migrations, the rescue_from error chain, and their RSpec specs. Triggers on any .rb change under src/backend/. Covers thin controllers + strong parameters, model-owned business logic and validations, the single ApplicationController rescue_from error shaper, routes-as-table, concerns extraction, and request/model specs. Generic Ruby fundamentals live in clean-code.
globs: "src/backend/**/*.rb"
depends_on:
  - clean-code
  - backend-fundamentals
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: This skill `depends_on: [clean-code, backend-fundamentals]`. `clean-code` gives universal code quality (fail-closed errors, typed exceptions, self-documenting code, error-path tests); `backend-fundamentals` gives stack-agnostic backend patterns (services, idempotency, envelopes, N+1, migrations, auth). This skill adds ONLY Ruby on Rails-specific layering on top.

# rails

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `config/routes.rb` | route helpers | controller bodies, models |
| `*_controller.rb` | the domain model, concerns | another controller, raw SQL |
| `app/models/*.rb` (ActiveRecord) | other models, the DB | controllers, `params`, `render` |
| `controllers/concerns/` | models (for auth lookups) | a specific controller's privates |

Controllers stay thin and transport-aware; models stay transport-free (no
`params`, no `render`) so they are unit-testable and the business logic survives
a transport swap (REST → GraphQL → ActionCable).

## Routes & controllers (thin)

- `config/routes.rb` is the single routing table — prefer `resources`/`resource`
  over hand-rolled `match`; one URL, one place.
- An action: strong-parameter the input (`params.require(:x).permit(:a, :b)`) →
  call ONE model method → `render`. No business branching, no multi-query loops.
- Subclass `ApplicationController`; never rescue-and-shape inside an action — raise
  a typed error and let the global chain map it.
- `before_action` filters load records / enforce auth; keep them in concerns when
  three controllers share them (rule of three), not copy-pasted.

## Models (ActiveRecord — the only layer that thinks)

- Business logic, scopes, and `validates` live on the model; a controller that
  validates by hand is a layering violation.
- Persist with `save!`/`create!`/`update!` so a failure raises and the
  `rescue_from` chain maps it — silent `save` that returns `false` hides errors.
- Migrations are reversible (`change`, or paired `up`/`down`); schema and data
  migrations stay in separate files. The agent writes them; the user runs `db:migrate`.

## Error handling

- ONE `rescue_from` chain in `ApplicationController` shapes every error response
  (RFC 9457 problem shape per `docs/api-contracts/error-format.md`).
  Unknown errors → 500 generic body, full detail to `logger` only — never a
  backtrace or SQL to the client.

## Testing

- Models: unit specs per public method (no HTTP) with transactional fixtures.
- Controllers: RSpec request specs against the Rack app — one happy + one
  error-path per endpoint minimum.
- Never bind a real server port in specs; drive the app through the request layer.
