<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Rails Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Rails backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [Rails Service Playbook](../playbooks/rails-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — route → controller → model. Controllers parse params and
   render; ActiveRecord models own business logic. Imports flow one way only
   (the table in the `rails` skill is the SSOT).
2. **Thin controllers** — an action that runs more than one query or branches on
   business state is a build-blocking review finding; push the logic to the model.
3. **One error shaper** — only the `rescue_from` chain in `ApplicationController`
   writes error bodies; it logs full detail and returns the problem shape with no
   internals (no backtraces, no SQL).
4. **Strong parameters fail-closed** — every action whitelists its fields with
   `params.require(...).permit(...)`; raw `params` never reaches `create`/`update`.
5. **Validations on the model** — data integrity lives in `validates`, not in the
   controller; a save that can fail uses `save!`/`create!` so the error chain maps it.
6. **Reversible migrations** — `change` when auto-reversible, otherwise paired
   `up`/`down`; schema and data migrations stay separate.
7. **No floating config** — environment access happens once at boot via
   `Rails.application.config`; models and controllers never read `ENV` inline.

## Testing bar

Models ≥ unit-spec per public method; controllers ≥ happy + error path via RSpec
request specs; database-touching code uses transactional fixtures, never a real port.
