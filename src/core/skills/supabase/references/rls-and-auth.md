<!-- domain:DB | layer:reference | ssot:true | updated:2026-06-04 -->
# Supabase RLS & Auth — Policies That Hold

> P: Write Row Level Security policies that enforce ownership correctly and stay fast.
> R: Adding a table, a policy, or debugging "users see each other's data".
> S: The token/session model itself — that's [auth-patterns](../../auth-patterns/SKILL.md).
> N: [SKILL.md](../SKILL.md), [realtime-and-storage.md](realtime-and-storage.md)

> Nav: [Skill](../SKILL.md)

## The four policy verbs

```sql
alter table notes enable row level security;

create policy "read own"   on notes for select using (auth.uid() = user_id);
create policy "insert own" on notes for insert with check (auth.uid() = user_id);
create policy "update own" on notes for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "delete own" on notes for delete using (auth.uid() = user_id);
```

`using` decides which existing rows a statement can see/touch; `with check`
validates the new row values on insert/update. `update` needs **both** — `using`
(can I touch this row?) and `with check` (is the result still mine?), or a user
could move a row to another owner.

## Always `auth.uid()`, never client input

```sql
-- Wrong — trusts a column the client controls; spoofable
create policy x on notes for select using (user_id = current_setting('request.user_id'));

-- Correct — auth.uid() comes from the verified JWT, not the request body
create policy x on notes for select using (auth.uid() = user_id);
```

`auth.uid()` derives from the signed JWT — the client cannot forge it.
`auth.jwt() ->> 'role'` exposes custom claims for role-based policies.

## Performance — RLS runs per row

A policy is a `WHERE` clause added to every query. Two rules keep it fast:

- **Index the policy column** (`user_id`) — without an index, every query is a
  seq scan filtered by the policy.
- **Wrap `auth.uid()` in a subquery** so Postgres evaluates it once, not per row:
  `using ((select auth.uid()) = user_id)`. This is the single biggest RLS perf win
  on large tables.

## Common shapes

| Need | Policy |
|---|---|
| owner-only | `auth.uid() = user_id` |
| team membership | `auth.uid() in (select user_id from team_members where team_id = notes.team_id)` |
| public read, owner write | select `using (true)`; insert/update `with check (auth.uid() = user_id)` |
| role-gated | `(auth.jwt() ->> 'role') = 'admin'` |
| soft-delete hidden | `using (deleted_at is null and auth.uid() = user_id)` |

## RLS enabled but no policy = locked, not open

Enabling RLS with **zero** policies denies all access (deny-by-default). That's
safe but usually a bug — you forgot the policies. `check_rls.py` catches the
opposite (RLS never enabled); for "enabled but empty" the symptom is "nobody can
read anything" — add the policies.
