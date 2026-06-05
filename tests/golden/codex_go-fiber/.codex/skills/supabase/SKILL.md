---
name: supabase
tier: stack
domain: [backend, db]
description: Build on Supabase correctly — Row Level Security, auth, realtime, storage, edge functions, and the Postgres underneath. Use when wiring a Supabase client, writing or reviewing RLS policies, debugging "anyone can read everyone's rows", setting up auth, adding realtime subscriptions, handling file storage, or deciding what belongs in an edge function vs the database. The #1 footgun — a table with RLS disabled is fully public — gets first-class coverage. Triggers — "Supabase", "RLS", "row level security", "policy", "anon key", "realtime subscription", "edge function", "supabase auth". Pairs with sql-authoring (the queries), db-design (the schema), auth-patterns (the token model), security-web (exposure review).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Supabase

Supabase is Postgres with a public API in front of it. That inversion is the whole risk model: the `anon` key ships to the browser, so **the database — not the application — is the security boundary**. Row Level Security is not optional hardening; it is the only thing standing between a user and everyone else's rows.

> Scan a migration for tables left without RLS:
> `python3 scripts/check_rls.py supabase/migrations/*.sql`

## RLS is the security boundary (enable it on every table)

```sql
-- Wrong — table is reachable via the anon key with NO policy = fully public
create table notes (id uuid primary key, user_id uuid, body text);

-- Correct — enable RLS, then policies grant the minimum
create table notes (id uuid primary key, user_id uuid references auth.users, body text);
alter table notes enable row level security;

create policy "owner reads own notes" on notes
  for select using (auth.uid() = user_id);
create policy "owner writes own notes" on notes
  for insert with check (auth.uid() = user_id);
```

A table created without `enable row level security` is readable and writable by
anyone holding the `anon` key — which is every visitor. Enable RLS on **every**
table in a public schema, then add policies. `using` filters which rows are
visible/updatable; `with check` validates rows being inserted/updated. Detail →
[references/rls-and-auth.md](references/rls-and-auth.md).

## The two keys — never confuse them

```
anon key        → ships to the browser. RLS applies. Safe to expose IF RLS is on.
service_role key → bypasses RLS entirely. SERVER ONLY. Never in client code, never in git.
```

```javascript
// Wrong — service_role in the browser = total database access for every visitor
const supabase = createClient(url, SERVICE_ROLE_KEY);   // in frontend code

// Correct — anon key client-side (RLS enforced); service_role only in a server/edge function
const supabase = createClient(url, ANON_KEY);
```

The `service_role` key bypasses all RLS — leaking it is a full database breach.
It belongs only in server-side code (edge functions, your backend) and a secret
store, never bundled to the client.

## Auth — `auth.uid()` is your policy anchor

Supabase Auth issues a JWT; inside RLS, `auth.uid()` returns the authenticated
user's id and `auth.jwt()` exposes claims. Policies key off these. The token
model (refresh rotation, session vs JWT, storage on mobile) is owned by
[auth-patterns](../auth-patterns/SKILL.md) — Supabase is one provider of that
model, not a replacement for understanding it.

## Realtime + storage — RLS still rules

```javascript
supabase.channel("notes")
  .on("postgres_changes", { event: "*", schema: "public", table: "notes" }, handler)
  .subscribe();
```

Realtime broadcasts only rows the subscriber's RLS lets them see — but you must
enable the table for realtime and keep RLS correct, or you leak via the socket.
Storage buckets have their own RLS-style policies; a "public" bucket is public to
the internet — default to private + signed URLs. Detail →
[references/realtime-and-storage.md](references/realtime-and-storage.md).

## Edge functions vs database

| Put it in the database | Put it in an edge function |
|---|---|
| row-level rules (RLS), constraints | calling a third-party API (Stripe, email) |
| triggers, computed columns | webhooks, server-only secrets |
| anything RLS can express | orchestration the client shouldn't see |

Push authorization into RLS and constraints (the database enforces them for every
client); use edge functions for server-only work and secrets. Don't reimplement in
an edge function what a policy already guarantees.

## Anti-patterns (reject on sight)

- A table in a public schema with RLS disabled → fully public; enable it.
- `service_role` key anywhere client-side or in git → full breach.
- RLS enabled but **no policy** → table is locked to everyone (also a bug — add policies).
- Trusting client-sent `user_id` in a policy instead of `auth.uid()` → spoofable.
- A "public" storage bucket for user uploads → internet-readable; private + signed URLs.
- Business authorization in the client/edge function that RLS should own → bypassed by a direct API call.

## See also

- [references/rls-and-auth.md](references/rls-and-auth.md) — policies, `auth.uid()`, performance, common policy shapes.
- [references/realtime-and-storage.md](references/realtime-and-storage.md) — channels, storage policies, signed URLs.
- [assets/supabase-checklist.md](assets/supabase-checklist.md) — the ship gate.
- [sql-authoring](../sql-authoring/SKILL.md) · [db-design](../db-design/SKILL.md) · [auth-patterns](../auth-patterns/SKILL.md) · [security-web](../security-web/SKILL.md).
