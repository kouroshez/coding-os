<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Rails Service Playbook

Purpose: The end-to-end recipe for adding or changing a Rails endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds a controller, route, ActiveRecord model, concern, or migration.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Rails Engineering Rules](../engineering/rails-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Route first** — declare the route in `config/routes.rb` (prefer `resources`
   over hand-rolled paths); the routing table stays the single place URLs live.
2. **Model** — `app/models/<domain>.rb`: an ActiveRecord class that owns its
   validations, scopes, and business logic. Persistence stays here, not in the
   controller.
3. **Controller** — `app/controllers/<domain>_controller.rb`: thin. Use strong
   parameters (`params.require(...).permit(...)`), call exactly one model method,
   then `render`. Raise a typed error on failure — never build an error body here.
4. **Error mapping** — failures surface as exceptions; the `rescue_from` chain in
   `ApplicationController` maps each to a status + the shared problem body
   ([error-format](../api-contracts/error-format.md)).
5. **Concern** — extract cross-cutting behavior (auth filters, pagination) into a
   module under `controllers/concerns/` only when three call sites need it.
6. **Migration** — `bin/rails generate migration` for schema changes; reversible
   (`change` or paired `up`/`down`). The agent writes it; the user runs `db:migrate`.
7. **Test** — RSpec request spec per endpoint (happy + error path) + a model spec
   per public method; never bind a real server port.
8. **Verify** — `cd src/backend && bundle exec rubocop && bundle exec rspec`.

## Global wiring (set once in `ApplicationController`)

`before_action` filters run auth/loading; the `rescue_from` chain is the single
error shaper. Every controller inherits both by subclassing `ApplicationController`.

## Anti-patterns

- Error JSON built inside an action — the `rescue_from` chain owns the shape.
- A fat controller running queries or business logic — that belongs in the model.
- Mass-assignment without strong parameters — every action permits its fields.
- Binding a real port in specs — use request specs against the Rack app.
