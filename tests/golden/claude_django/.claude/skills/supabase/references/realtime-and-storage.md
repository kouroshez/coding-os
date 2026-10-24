<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Supabase Realtime & Storage

> P: Stream row changes and serve files without leaking past RLS.
> R: Adding a realtime subscription or file upload/download.
> S: Table policies themselves — see [rls-and-auth.md](rls-and-auth.md).
> N: [SKILL.md](../SKILL.md), [supabase-checklist.md](../assets/supabase-checklist.md)

> Nav: [Skill](../SKILL.md)

## Realtime — RLS still filters the stream

```javascript
const channel = supabase
  .channel("room:1")
  .on("postgres_changes",
      { event: "INSERT", schema: "public", table: "messages", filter: "room_id=eq.1" },
      (payload) => render(payload.new))
  .subscribe();
// later: supabase.removeChannel(channel)
```

Realtime delivers a change only if the subscriber's RLS would let them `select`
that row — so correct policies protect the socket too. You must enable the table
for the realtime publication (`alter publication supabase_realtime add table
messages`). Always `removeChannel` on unmount or you leak subscriptions.

## Storage — buckets are RLS for files

```sql
-- private bucket + a policy: users read only their own folder
create policy "own folder read" on storage.objects for select
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
```

A bucket marked **public** is readable by anyone with the URL — fine for static
assets, a breach for user uploads. Default to **private** buckets and hand out
**signed URLs** with a short expiry:

```javascript
const { data } = await supabase.storage.from("avatars").createSignedUrl(path, 60);
```

Never build a public URL for private content. Validate upload size/MIME
server-side (an edge function or a storage policy) — the client check is advisory.

## Generated types — keep the client honest

```bash
supabase gen types typescript --project-id <id> > types/database.ts
```

Generate TypeScript types from the live schema so the client's row shapes can't
drift from the database (the api-contract-discipline rule, applied to Supabase).
Re-generate after every migration; a stale type is a silent `undefined` at runtime.
