<!-- domain:FRONTEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Rendering & State — Re-renders, Keys, Data Fetching

> P: Control when components re-render and where state lives, framework-agnostically.
> R: Building or debugging any component (slow renders, stale UI, lost input).
> S: Framework-specific routing/SSR — that's your stack skill (nextjs-react / react-native).
> N: [SKILL.md](../SKILL.md), [frontend-checklist.md](../assets/frontend-checklist.md)

> Nav: [Skill](../SKILL.md)

## Why a component re-renders (and how to stop the wasted ones)

A component re-renders when its state/props change. The common waste: a parent
passes a **new reference** every render.

```jsx
// Wrong — {} and () => are new each render → child re-renders even if "the same"
<Child style={{ margin: 4 }} onClick={() => save(id)} />

// Correct — stable references
const style = useMemo(() => ({ margin: 4 }), []);
const onClick = useCallback(() => save(id), [id]);
<Child style={style} onClick={onClick} />
```

`check_frontend.py` flags inline object/array props and other smells. Don't
memoize *everything* (the bookkeeping costs too) — memoize references passed to
memoized children or used in dependency arrays.

## Keys — stable identity, never the index

```jsx
// Wrong — index key: reorder/insert corrupts state + DOM reuse
{items.map((it, i) => <Row key={i} item={it} />)}

// Correct — a stable id from the data
{items.map((it) => <Row key={it.id} item={it} />)}
```

The key tells the reconciler which item is which across renders. The array index
changes when the list reorders, so React reuses the wrong DOM/state. Use a stable
unique id.

## State lives at the lowest common ancestor

Put state as close to where it's used as possible; lift it only to the nearest
parent that *both* consumers share. State too high re-renders a whole subtree on
every keystroke; too low can't be shared. The full layer model (server-state vs
client-state vs URL vs local) is owned by
[state-management](../../state-management/SKILL.md).

## Controlled inputs + data fetching

- **Controlled inputs**: value comes from state, `onChange` updates it — one
  source of truth. Forgetting `onChange` makes a read-only input (a classic "my
  typing doesn't work" bug).
- **Server data is not component state**: fetch with a server-state library
  (TanStack Query) that handles caching, dedup, refetch, and loading/error —
  don't hand-roll `useEffect` + `useState` for every request (race conditions,
  no cache, waterfalls).

## Lists + performance

Virtualize long lists (render only what's visible). Avoid layout thrash (batch DOM
reads then writes). Code-split heavy routes/components (lazy load). The measured
Web-Vitals/profiling craft is owned by [performance](../../performance/SKILL.md).
