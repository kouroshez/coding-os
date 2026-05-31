---
name: state-management
description: Choose and implement state management for React Native + React + Vue + Svelte clients. Use when adding any client state — server-cache, global UI state, form state, navigation state. Covers the layer hierarchy (server-state vs client-state vs URL state vs local state), Zustand / Redux Toolkit / MobX / Pinia / Riverpod recipes, TanStack Query as the server-state layer, persistence + hydration, derived-state pitfalls, anti-patterns. Pairs with hexagonal-architecture (state lives in delivery, never in domain).
tier: cross-cutting
domain: [frontend, mobile]
last_reviewed: "2026-05-11"

---

# State Management — Pick the Right Layer

Most "state management" debates collapse once you split state into the four kinds it actually has. This skill makes that split explicit and prescribes a tool per layer. Stack-agnostic; concrete recipes target React / React Native (this project's UI stack) with Pinia / Riverpod / Svelte runes callouts where they differ.

## When to Use This Skill

- Adding any new client-side state.
- Promoting a `useState` to a wider scope.
- Choosing a tool for a new app (Zustand vs Redux Toolkit vs Jotai vs MobX vs Riverpod vs Pinia).
- Reviewing a PR that introduces a global store.
- Untangling a "state tree" that's grown into a god-object.
- Adding persistence (write to MMKV / localStorage / AsyncStorage) to a store.

## The Four Kinds of State

The single most important framing. Everything else falls out of it.

| Kind | Owner | Tool (React/RN) | Lifetime | Examples |
|---|---|---|---|---|
| **Server state** | The server | TanStack Query | Cached + revalidated | List of orders, current user profile, unread count |
| **URL state** | The router | React Navigation / Next router | URL-bound | Selected tab, filter query, modal open flag |
| **Global UI state** | The store | Zustand (default) | App session | Theme, locale, sidebar open, toast queue |
| **Local component state** | The component | `useState` / `useReducer` | Component instance | Input value, hover state, expanded accordion |

Most app state is **server state**. Treating it as anything else (loading flags, "user data" globals, etc.) is the #1 cause of stale-data bugs. The default move: TanStack Query first; reach for a global store only when server-state doesn't fit.

## The Decision Flow

```
"Where does this state come from?"
├─ Comes from the server (or could) → TanStack Query (server state)
├─ Should be reflected in URL → router params / search params (URL state)
├─ Used by 2+ unrelated screens AND not server-derivable → Global store (Zustand)
└─ Used by one component → useState / useReducer (local state)
```

If you find yourself saying "but I also want to cache the server response in my Zustand store"... stop. That's TanStack Query's job. Use one tool per layer, not two.

## Server State — TanStack Query

The default for ANY data that originates from the server. Replaces homegrown loading-flag-and-spinner code, manual refetch logic, and most of what people use Redux for.

### Minimum Setup (RN)

```typescript
// App.tsx
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { useEffect, useMemo } from 'react';

// Bridge React Query's focus + online detection to RN's events.
onlineManager.setEventListener((setOnline) => {
  return NetInfo.addEventListener((state) => setOnline(!!state.isConnected));
});

focusManager.setEventListener((handleFocus) => {
  const sub = AppState.addEventListener('change', (s) => handleFocus(s === 'active'));
  return () => sub.remove();
});

export default function App() {
  const queryClient = useMemo(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,            // serve from cache 30s before refetch
        gcTime: 24 * 3600_000,         // keep cache 24h after unmount
        retry: (count, err) => isNetworkError(err) && count < 3,
        networkMode: 'offlineFirst',
      },
      mutations: {
        retry: false,                  // mutations have explicit retry logic in sync queue
      },
    },
  }), []);

  return (
    <QueryClientProvider client={queryClient}>
      <RootNavigator />
    </QueryClientProvider>
  );
}
```

### Query Pattern

```typescript
// mobile/src/delivery/screens/lesson/LessonScreen.tsx
import { useQuery } from '@tanstack/react-query';

export function LessonScreen({ route }: LessonScreenProps) {
  const lessonId = route.params.lessonId;
  const getLesson = useUseCase('getLesson');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lesson', lessonId],
    queryFn: () => getLesson.execute({ lessonId }),
    enabled: !!lessonId,
  });

  if (isLoading) return <CenteredSpinner />;
  if (isError)   return <ErrorState message={error.message} onRetry={refetch} />;
  if (!data)     return null;
  return <LessonView lesson={data} />;
}
```

### Mutation Pattern (Online-First)

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';

export function useUpdateLesson(lessonId: string) {
  const queryClient = useQueryClient();
  const updateLesson = useUseCase('updateLesson');

  return useMutation({
    mutationFn: (input: UpdateLessonInput) => updateLesson.execute(input),
    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: ['lesson', lessonId] });
      const prev = queryClient.getQueryData<Lesson>(['lesson', lessonId]);
      queryClient.setQueryData<Lesson>(['lesson', lessonId], (old) => old ? { ...old, ...input } : old);
      return { prev };
    },
    onError: (_err, _input, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['lesson', lessonId], ctx.prev);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['lesson', lessonId] });
    },
  });
}
```

### Mutation Pattern (Offline-First)

For RN apps with offline support, mutations go through the sync queue (see `mobile-fundamentals` offline section). The use case writes to local cache + enqueues; the worker drains it. TanStack Query reads from local cache.

### Query Key Conventions

Hierarchical, sortable, predictable:

```typescript
// All lessons
['lessons']

// One lesson
['lesson', lessonId]

// One user's lessons
['users', userId, 'lessons']

// Filtered list
['lessons', { status: 'completed', limit: 20 }]
```

Filter objects must be deeply-equal-stable (don't pass new object literals into `useQuery` — wrap in `useMemo`).

For canonical key shapes per resource, see [references/tanstack-query-recipes.md](references/tanstack-query-recipes.md).

### Common TanStack Mistakes

1. **Storing query data in Zustand** — defeats the cache; use `queryClient` directly.
2. **Mutating data inside `select`** — selectors must be pure.
3. **Refetching on every render** — usually a stale `enabled` calculation; pin with `useMemo`.
4. **No `staleTime`** — refetches on every mount; mobile users see flicker.
5. **No `queryKey` namespace** per resource — collisions across screens.
6. **`useQuery` inside a non-component (utility function)** — error: hooks rule.

## Global UI State — Zustand (Default)

Use for: theme, locale, auth status, toast queue, sidebar open. Things shared across unrelated components that don't belong on the server.

### Setup

```typescript
// mobile/src/delivery/state/themeStore.ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { MMKV } from 'react-native-mmkv';

const mmkv = new MMKV({ id: 'theme' });
const mmkvStorage = {
  getItem: (key: string) => mmkv.getString(key) ?? null,
  setItem: (key: string, value: string) => mmkv.set(key, value),
  removeItem: (key: string) => mmkv.delete(key),
};

interface ThemeState {
  mode: 'light' | 'dark' | 'system';
  setMode: (mode: ThemeState['mode']) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'system',
      setMode: (mode) => set({ mode }),
    }),
    {
      name: 'theme-store',
      storage: createJSONStorage(() => mmkvStorage),
      partialize: (state) => ({ mode: state.mode }),  // only persist `mode`
      version: 1,
    }
  )
);
```

### Selector Discipline

Always select the slice you need; selectors are the way to avoid unnecessary re-renders.

```typescript
// BAD — re-renders on ANY store change.
const theme = useThemeStore();

// GOOD — re-renders only when `mode` changes.
const mode = useThemeStore((s) => s.mode);

// GOOD — derived; only re-renders when the derived value changes.
const isDark = useThemeStore((s) => s.mode === 'dark' || (s.mode === 'system' && systemColorScheme === 'dark'));
```

For multiple slices, use multiple `useStore` calls — Zustand handles equality checks fine.

### Multiple Stores (Domain-Split)

Don't put everything in one store. Split by concern:

```
mobile/src/delivery/state/
├── themeStore.ts        # theme, locale, accessibility prefs
├── authStore.ts         # current user, session token (in-memory only)
├── toastStore.ts        # global toast queue
├── networkStore.ts      # online/offline + pending sync count
└── notificationStore.ts # in-app notification queue
```

Each store is single-purpose, ~50-100 LOC. Combined surface area scales linearly, not quadratically.

### What NOT to Put in Zustand

- **Server data** — TanStack Query.
- **Route state** — React Navigation.
- **Form state** — React Hook Form.
- **Component-only state** — `useState`.
- **Refs / DOM nodes** — `useRef`.
- **Function arguments / event payloads** — pass via props/callbacks.

For the full Zustand patterns including async actions, computed values, and selector composition, see [references/zustand-recipes.md](references/zustand-recipes.md).

## When NOT Zustand — Other Options

### Redux Toolkit (RTK)

- ✅ Existing Redux app you're maintaining.
- ✅ Time-travel debugging required (DevTools is unmatched).
- ✅ Strict event-sourcing / undo-redo / replay.
- ❌ New project — Zustand wins on lines-of-code.
- ❌ Mobile (extra render overhead vs Zustand).

### Jotai (Atoms)

- ✅ Many small, independent pieces of state with derivations.
- ✅ Suspense-friendly async patterns.
- ❌ State that's coordinated across many actions (god-atom risk).

### MobX

- ✅ Domain models with rich behavior + observation (Vue 2-style).
- ✅ Highly mutable state graphs.
- ❌ Functional / immutable preferred.
- ❌ React Server Components (decorator + observable doesn't play well).

### Valtio

- ✅ Mutation-style API with proxy magic.
- ❌ Niche; smaller ecosystem.

### XState

- ✅ Explicit state machines required (checkout flow, complex form).
- ✅ Visualizing state transitions.
- ❌ Simple state — overkill.
- ❌ Most CRUD UI.

### Riverpod (Flutter)

- ✅ Default for new Flutter apps.
- Hooks-equivalent; provider / notifier / asyncNotifier patterns.

### Pinia (Vue)

- ✅ Default for Vue 3 — cleaner than Vuex 4.
- Composition API + setup syntax.

### Svelte Runes ($state, $derived)

- ✅ Built-in — Svelte 5+ runes are the state mechanism.
- Don't add Zustand to Svelte; use stores or runes.

## Forms — React Hook Form (RN/React)

Form state is its OWN thing. Don't put form values in Zustand or local `useState`.

```typescript
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const Schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

type FormData = z.infer<typeof Schema>;

export function SignInForm() {
  const { control, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<FormData>({ resolver: zodResolver(Schema) });

  const signIn = useUseCase('signIn');

  const onSubmit = async (data: FormData) => {
    await signIn.execute(data);
  };

  return (
    <View>
      <Controller name="email" control={control} render={({ field }) => (
        <TextInput value={field.value} onChangeText={field.onChange} onBlur={field.onBlur} />
      )} />
      ...
      <Button title="Sign In" onPress={handleSubmit(onSubmit)} disabled={isSubmitting} />
    </View>
  );
}
```

Why React Hook Form:
- Uncontrolled by default — fewer re-renders per keystroke.
- Validation via Zod (or Valibot) at the boundary.
- Composable across nested fields.
- Tiny bundle.

## URL State — Router Owns It

If a state is bookmarkable / shareable / restorable, put it in the URL.

```typescript
// React Navigation params
navigation.navigate('Lessons', { filter: 'completed', tag: 'react' });
const { filter, tag } = route.params;

// Or update without re-navigating:
navigation.setParams({ filter: 'completed' });
```

Don't mirror URL state into Zustand. The router IS the source of truth. If you need to derive UI state from a route param, use `useRoute()` directly in components or a small hook:

```typescript
function useFilter() {
  const route = useRoute<LessonsScreenProps['route']>();
  return route.params.filter ?? 'all';
}
```

## Hexagonal Hook-up

State management lives in the **delivery** layer. NEVER:

- Import a Zustand store from `application/`.
- Reference `useQuery` inside a use case.
- Put TanStack Query keys in `domain/`.

Use cases take dependencies via constructor injection (per `hexagonal-architecture` skill). The delivery layer wires them and triggers them via React hooks. Stores cache the OUTPUT of use case calls; they don't replace use cases.

```typescript
// CORRECT
function useLesson(lessonId: LessonID) {
  const getLesson = useUseCase('getLesson');
  return useQuery({
    queryKey: ['lesson', lessonId],
    queryFn: () => getLesson.execute({ lessonId }),
  });
}

// WRONG — store calls Axios directly, bypasses use case + hexagonal layering
const useLessonStore = create((set) => ({
  fetch: async (id) => {
    const res = await axios.get(`/lessons/${id}`);
    set({ lesson: res.data });
  },
}));
```

## Common State Management Mistakes

1. **One global store for everything** — god object; every change re-renders the world.
2. **Server data in Zustand** — TanStack Query exists, use it.
3. **Form values in a store** — every keystroke is a global re-render.
4. **`useEffect` to "sync" two states** — usually means one of them shouldn't exist.
5. **Mutating store state** — Zustand uses Immer in middleware; otherwise treat state as immutable.
6. **Subscribing to whole store** instead of selecting — re-renders on unrelated changes.
7. **Derived state stored** — recompute, don't cache. Memoize the EXPENSIVE part only.
8. **Store actions calling other stores** — tight coupling. Use events or a coordinator hook.
9. **Persisting too much** — only persist what you need restored across launches.
10. **No store version** — schema change → corrupt persisted state on user devices.
11. **Async work in component, result in store, used in same render** — race conditions; use TanStack Query.
12. **`useStore.getState()` in render** — bypasses subscription; component doesn't re-render on change.

## Source Material

- TanStack Query docs (v5) — primary source for server state.
- Zustand README + recipes — single source of truth for the lib.
- *State Management for React/RN* — Kent C. Dodds, Mark Erikson (Redux maintainer) blog series.
- TkDodo's blog — TanStack Query patterns: <https://tkdodo.eu/blog/all>
- Riverpod docs (Flutter) and Pinia docs (Vue) for cross-framework guidance.
