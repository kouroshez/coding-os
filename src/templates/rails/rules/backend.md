# Rails Backend Rules (auto-loaded for src/backend/**/*.rb)

> Controllers thin, ActiveRecord models own logic, ONE `rescue_from` chain shapes
> every error. Full conventions: [rails-rules.md](../scaffold/docs/engineering/rails-rules.md).

- Route → controller → model; imports flow one way only.
- Strong parameters on every write action; raw `params` never reaches the model.
- Validations live on the model (`validates`), not in the action.
- Only `ApplicationController`'s `rescue_from` chain writes error bodies.
- Reversible migrations; schema and data migrations stay separate.
