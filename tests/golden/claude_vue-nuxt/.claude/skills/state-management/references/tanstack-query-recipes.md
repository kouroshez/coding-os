# TanStack Query — Recipe Book

Patterns that come up over and over in real apps. Each one is something you'll grep for at 11pm.

## Query Key Conventions

Hierarchical, sortable, predictable. Use the **factory pattern** for type-safety.

```typescript
// mobile/src/delivery/queries/keys.ts
export const queryKeys = {
  lessons: {
    all:          ['lessons'] as const,
    lists:        () => [...queryKeys.lessons.all, 'list'] as const,
    list:         (filters: LessonFilters) => [...queryKeys.lessons.lists(), filters] as const,
    details:      () => [...queryKeys.lessons.all, 'detail'] as const,
    detail:       (id: LessonID) => [...queryKeys.lessons.details(), id] as const,
    completion:   (id: LessonID) => [...queryKeys.lessons.detail(id), 'completion'] as const,
  },
  user: {
    all:     ['user'] as const,
    me:      () => [...queryKeys.user.all, 'me'] as const,
    profile: (id: UserID) => [...queryKeys.user.all, id, 'profile'] as const,
  },
} as const;

// Usage:
useQuery({ queryKey: queryKeys.lessons.detail(id), queryFn: () => ... });

// Invalidate all lesson queries:
queryClient.invalidateQueries({ queryKey: queryKeys.lessons.all });

// Invalidate just lists (not details):
queryClient.invalidateQueries({ queryKey: queryKeys.lessons.lists() });
```

## `staleTime` vs `gcTime`

- **`staleTime`** — how long the data is considered fresh. Within this window, refetch on remount is skipped.
- **`gcTime`** — how long unused query data lives in the cache before garbage collection.

| Type of data | `staleTime` | `gcTime` |
|---|---|---|
| User profile (rarely changes) | 5 min | 24 h |
| Lesson list | 30 sec | 24 h |
| Real-time chat messages | 0 (always stale → refetch) | 1 h |
| Static config (feature flags) | 5 min | 24 h |
| Search results | 0 | 5 min (low value) |

## Infinite Queries (Cursor Pagination)

```typescript
import { useInfiniteQuery } from '@tanstack/react-query';

export function useLessons(filter: LessonFilter) {
  return useInfiniteQuery({
    queryKey: queryKeys.lessons.list(filter),
    queryFn: ({ pageParam }) => listLessons.execute({ filter, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,  // null = no more
    staleTime: 30_000,
  });
}

// In the screen:
const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useLessons(filter);
const items = data?.pages.flatMap((p) => p.data) ?? [];

<FlashList
  data={items}
  estimatedItemSize={88}
  onEndReached={() => hasNextPage && !isFetchingNextPage && fetchNextPage()}
  onEndReachedThreshold={0.5}
/>
```

## Prefetch on Navigation

```typescript
// On the list screen, prefetch the detail when the user touches a row.
const onPressLesson = (lesson: Lesson) => {
  queryClient.prefetchQuery({
    queryKey: queryKeys.lessons.detail(lesson.id),
    queryFn: () => getLesson.execute({ lessonId: lesson.id }),
    staleTime: 60_000,
  });
  navigation.navigate('Lesson', { lessonId: lesson.id });
};
```

When the detail screen mounts, the data is already there — no spinner.

## Dependent Queries

Query B needs the result of Query A. Use `enabled`.

```typescript
const { data: user } = useQuery({ queryKey: queryKeys.user.me(), queryFn: fetchMe });
const { data: lessons } = useQuery({
  queryKey: queryKeys.lessons.list({ userId: user?.id }),
  queryFn: () => listLessons.execute({ userId: user!.id }),
  enabled: !!user?.id,
});
```

## `useMutation` Flow with Cache Updates

```typescript
const completeLesson = useMutation({
  mutationFn: (input: { lessonId: LessonID }) => completeLessonUseCase.execute(input),

  // Optimistic UI: snapshot, write the optimistic value.
  onMutate: async ({ lessonId }) => {
    await queryClient.cancelQueries({ queryKey: queryKeys.lessons.detail(lessonId) });
    const prev = queryClient.getQueryData<Lesson>(queryKeys.lessons.detail(lessonId));
    queryClient.setQueryData<Lesson>(queryKeys.lessons.detail(lessonId), (old) =>
      old ? { ...old, state: 'completed' } : old
    );
    return { prev };
  },

  // Rollback on failure.
  onError: (_err, { lessonId }, ctx) => {
    if (ctx?.prev) queryClient.setQueryData(queryKeys.lessons.detail(lessonId), ctx.prev);
  },

  // Always sync with server truth.
  onSettled: (_data, _err, { lessonId }) => {
    queryClient.invalidateQueries({ queryKey: queryKeys.lessons.detail(lessonId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.lessons.lists() });
  },
});
```

## Polling

```typescript
const { data } = useQuery({
  queryKey: ['order', orderId],
  queryFn: () => getOrder.execute({ orderId }),
  refetchInterval: (query) => {
    const order = query.state.data;
    if (!order) return 5_000;
    if (order.status === 'paid' || order.status === 'failed') return false;  // stop polling
    return 3_000;
  },
});
```

The `refetchInterval` callback gets the current query state — return `false` to stop.

## Suspense Mode (Optional)

For React 19 / RN 0.76+ with Suspense support, opt in per query:

```typescript
import { useSuspenseQuery } from '@tanstack/react-query';

function Lesson({ id }: { id: LessonID }) {
  // No isLoading; component suspends until data is ready.
  const { data } = useSuspenseQuery({ queryKey: queryKeys.lessons.detail(id), queryFn: ... });
  return <Text>{data.title}</Text>;
}

// In the parent:
<Suspense fallback={<CenteredSpinner />}>
  <Lesson id={lessonId} />
</Suspense>
<ErrorBoundary fallback={<ErrorState />}>
  ...
</ErrorBoundary>
```

Cleaner code, but you give up granular per-query loading UI. Use selectively.

## Network-Aware Behavior

```typescript
// Disable retries when offline (avoids futile attempts):
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      networkMode: 'offlineFirst',   // serve cache when offline
      retry: 3,
    },
    mutations: {
      networkMode: 'offlineFirst',   // queue mutation when offline (paired with retry)
    },
  },
});
```

For full offline-first with a sync queue, see `mobile-fundamentals` offline section.

## Persistence Across App Launches

```typescript
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { MMKV } from 'react-native-mmkv';

const mmkv = new MMKV({ id: 'tanstack-query' });
const persister = createSyncStoragePersister({
  storage: {
    getItem: (k) => mmkv.getString(k) ?? null,
    setItem: (k, v) => mmkv.set(k, v),
    removeItem: (k) => mmkv.delete(k),
  },
});

<PersistQueryClientProvider client={queryClient} persistOptions={{
  persister,
  maxAge: 24 * 3600_000,
  buster: APP_VERSION,           // bust on app update
  dehydrateOptions: {
    shouldDehydrateQuery: (q) => q.state.status === 'success' && q.queryKey[0] !== 'auth',
  },
}}>
  <RootNavigator />
</PersistQueryClientProvider>
```

Don't persist auth state via TanStack — keep it in memory + Keychain.

## Selectors (Render Optimization)

```typescript
// Re-renders only when `title` changes, not the whole lesson.
const title = useQuery({
  queryKey: queryKeys.lessons.detail(id),
  queryFn: () => getLesson.execute({ lessonId: id }),
  select: (lesson) => lesson.title,
});
```

The `select` runs on every fetch but only re-renders the component when the SELECTED value's identity changes. Memoize complex selectors with `useCallback`.

## Cancel In-Flight on Unmount

Default behavior — TanStack cancels stale queries when the component unmounts. To make this work with your `queryFn`, propagate the abort signal:

```typescript
useQuery({
  queryKey: ['big-doc', id],
  queryFn: ({ signal }) => fetch(`/docs/${id}`, { signal }).then((r) => r.json()),
});
```

Pass `signal` to `axios`, `fetch`, your API client. Saves bandwidth and prevents stale state-set on unmounted components.

## Error Boundaries

Pair with React's `ErrorBoundary` (or `react-error-boundary`):

```typescript
import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { ErrorBoundary } from 'react-error-boundary';

<QueryErrorResetBoundary>
  {({ reset }) => (
    <ErrorBoundary
      onReset={reset}
      fallbackRender={({ resetErrorBoundary }) => (
        <View>
          <Text>Something went wrong</Text>
          <Button title="Retry" onPress={resetErrorBoundary} />
        </View>
      )}
    >
      <Lesson id={lessonId} />
    </ErrorBoundary>
  )}
</QueryErrorResetBoundary>
```

Set `throwOnError: true` on queries that should propagate to the boundary instead of returning `error` state.

## Devtools (RN)

```bash
yarn add -D @tanstack/react-query-devtools react-native-flipper
```

Plug into Flipper or use the standalone DevTools webview. Indispensable for debugging cache state.

## Anti-Patterns

1. **Mixing query data with Zustand** — pick one home for each piece of data.
2. **`refetchOnMount: 'always'`** + short staleTime — every screen mount = network call.
3. **Stringly-typed query keys** (`['lesson-' + id]`) — defeats invalidation patterns.
4. **`enabled: !!data && !!otherData && condition3`** — extract to a `useMemo` boolean.
5. **`queryFn` defined inline (new ref every render)** — TanStack handles this OK but it's confusing; use named functions.
6. **`useQuery` with no `queryKey`** — won't compile; runtime if dynamic.
7. **`onSuccess` doing navigation** — race conditions; do navigation in the component effect or via mutation callback.
8. **Shoehorning subscriptions (WebSocket) into `useQuery`** — use a custom hook that updates `queryClient.setQueryData` from the socket; keep `useQuery` as the read interface.

## Source Material

- TanStack Query v5 docs — primary source.
- TkDodo's blog (Dominik Dorfmeister, TanStack maintainer): <https://tkdodo.eu/blog/all>
- Mark Erikson — *Why I Prefer React Query Over Redux for Server State*.
