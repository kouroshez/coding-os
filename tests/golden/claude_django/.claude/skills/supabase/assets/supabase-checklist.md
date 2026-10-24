<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Supabase Ship Checklist

Run before exposing a Supabase project.

## Security (the boundary is the database)
- [ ] Every table in a public schema has `enable row level security`.
- [ ] `python3 scripts/check_rls.py supabase/migrations/*.sql` → `clean`.
- [ ] Every RLS table has policies (enabled-but-empty = locked, also a bug).
- [ ] Policies use `auth.uid()`/`auth.jwt()`, never client-supplied identity.
- [ ] `update` policies have BOTH `using` and `with check`.
- [ ] `service_role` key is server-only — not in client code, not in git, in a secret store.
- [ ] Storage buckets for user content are private + signed URLs (not public).

## Performance
- [ ] Policy filter columns (`user_id`, `team_id`) are indexed.
- [ ] `auth.uid()` wrapped in `(select auth.uid())` in hot-table policies.

## Correctness
- [ ] Realtime tables added to the publication; channels removed on unmount.
- [ ] TypeScript types regenerated after the latest migration (`supabase gen types`).
- [ ] Authorization lives in RLS/constraints, not only in client/edge code.

## Verify
- [ ] Tested as an anon user: can read/write only own rows.
- [ ] `make skills-check-versions` — Supabase CLI pin current.
