# Zustand — Recipe Book

Patterns for global UI state. Cross-platform (React + RN); examples target RN with MMKV persistence.

## Minimum Store

```typescript
// mobile/src/delivery/state/themeStore.ts
import { create } from 'zustand';

interface ThemeState {
  mode: 'light' | 'dark' | 'system';
  setMode: (mode: ThemeState['mode']) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: 'system',
  setMode: (mode) => set({ mode }),
}));
```

That's it. No provider, no boilerplate. Use anywhere:

```typescript
const mode = useThemeStore((s) => s.mode);
const setMode = useThemeStore((s) => s.setMode);
```

## Selector Discipline

The single biggest performance lever. Always select; never grab the whole store.

```typescript
// BAD — re-renders on ANY state change.
const store = useThemeStore();

// GOOD — re-renders only when `mode` changes.
const mode = useThemeStore((s) => s.mode);

// Multi-slice — call useStore twice; it does shallow equality per call.
const mode = useThemeStore((s) => s.mode);
const accent = useThemeStore((s) => s.accent);

// Or use `useShallow` for object slices:
import { useShallow } from 'zustand/react/shallow';
const { mode, accent } = useThemeStore(useShallow((s) => ({ mode: s.mode, accent: s.accent })));
```

## Persistence (MMKV in RN)

```typescript
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { MMKV } from 'react-native-mmkv';

const mmkv = new MMKV({ id: 'app' });
const mmkvStorage = {
  getItem:    (key: string) => mmkv.getString(key) ?? null,
  setItem:    (key: string, value: string) => { mmkv.set(key, value); },
  removeItem: (key: string) => { mmkv.delete(key); },
};

interface SettingsState {
  notifications: { lessons: boolean; social: boolean };
  hapticEnabled: boolean;
  toggleLessons: () => void;
  toggleSocial: () => void;
  setHaptic: (on: boolean) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      notifications: { lessons: true, social: false },
      hapticEnabled: true,
      toggleLessons: () => set((s) => ({
        notifications: { ...s.notifications, lessons: !s.notifications.lessons },
      })),
      toggleSocial: () => set((s) => ({
        notifications: { ...s.notifications, social: !s.notifications.social },
      })),
      setHaptic: (on) => set({ hapticEnabled: on }),
    }),
    {
      name: 'settings-store',
      version: 1,
      storage: createJSONStorage(() => mmkvStorage),
      // Only persist what the user expects restored:
      partialize: (state) => ({
        notifications: state.notifications,
        hapticEnabled: state.hapticEnabled,
      }),
      // On bumped version: migrate or wipe.
      migrate: (persisted: any, prevVersion) => {
        if (prevVersion < 1) {
          return { ...persisted, hapticEnabled: persisted.haptic ?? true };
        }
        return persisted;
      },
    }
  )
);
```

Web equivalent: replace MMKV with `localStorage` (`createJSONStorage(() => localStorage)`).

### What NEVER to Persist

- **Auth tokens** — Keychain only.
- **PII** — encrypt at rest if persisted.
- **Server data** — TanStack Query has its own persistence.
- **Transient UI state** — toast queue, modal-open flags.

## Async Actions

Async logic in actions is fine — Zustand doesn't care about returns being promises.

```typescript
interface AuthState {
  user: User | null;
  status: 'idle' | 'loading' | 'authenticated' | 'error';
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  status: 'idle',
  error: null,

  signIn: async (email, password) => {
    set({ status: 'loading', error: null });
    try {
      const user = await signInUseCase.execute({ email, password });
      set({ user, status: 'authenticated' });
    } catch (e) {
      set({ status: 'error', error: e.message });
      throw e;
    }
  },

  signOut: async () => {
    await signOutUseCase.execute();
    set({ user: null, status: 'idle', error: null });
  },
}));
```

⚠️ But beware: at this point you're rebuilding TanStack Query. For server-state patterns (loading states, retries, dedupe, cache), use TanStack Query. Use Zustand for auth-status flag + user pointer; keep the actual user data flowing through `useQuery({ queryKey: ['user', 'me'] })`.

## Computed Values

For derived state that's used in multiple places, compute INSIDE the selector:

```typescript
// Don't add `isAuthenticated: boolean` to the store — derive it.
const isAuthenticated = useAuthStore((s) => s.status === 'authenticated' && s.user !== null);
```

For expensive derivations, memoize in the consumer:

```typescript
const messages = useMessagesStore((s) => s.messages);
const sortedMessages = useMemo(() => {
  return [...messages].sort((a, b) => b.createdAt - a.createdAt);
}, [messages]);
```

For derived state used in a SELECTOR, use `zustand/middleware/computed` (from third-party libs) or just pre-compute in the action:

```typescript
const useCartStore = create((set) => ({
  items: [],
  total: 0,
  add: (item) => set((s) => {
    const items = [...s.items, item];
    return { items, total: items.reduce((sum, i) => sum + i.price, 0) };
  }),
}));
```

The pre-compute pattern keeps `total` always-fresh without a separate selector.

## Subscribing Outside React

```typescript
import { useThemeStore } from './themeStore';

// One-shot read:
const currentMode = useThemeStore.getState().mode;

// Subscribe to changes (e.g., in a non-React module like an analytics SDK):
const unsub = useThemeStore.subscribe(
  (state) => state.mode,
  (mode, prevMode) => {
    if (mode !== prevMode) analytics.track('theme_changed', { mode });
  }
);
// unsub() to stop.
```

Never call `useThemeStore.getState()` inside a component — bypasses subscription. Use the hook.

## Slicing Big Stores

Once a store grows past ~150 LOC, split into slices:

```typescript
// mobile/src/delivery/state/slices/themeSlice.ts
import type { StateCreator } from 'zustand';

export interface ThemeSlice {
  mode: 'light' | 'dark' | 'system';
  setMode: (m: ThemeSlice['mode']) => void;
}

export const createThemeSlice: StateCreator<ThemeSlice & SettingsSlice, [], [], ThemeSlice> =
  (set) => ({
    mode: 'system',
    setMode: (mode) => set({ mode }),
  });
```

```typescript
// mobile/src/delivery/state/slices/settingsSlice.ts
export interface SettingsSlice {
  hapticEnabled: boolean;
  setHaptic: (on: boolean) => void;
}

export const createSettingsSlice: StateCreator<ThemeSlice & SettingsSlice, [], [], SettingsSlice> =
  (set) => ({
    hapticEnabled: true,
    setHaptic: (on) => set({ hapticEnabled: on }),
  });
```

```typescript
// mobile/src/delivery/state/userPrefsStore.ts
import { create } from 'zustand';
import { createThemeSlice, type ThemeSlice } from './slices/themeSlice';
import { createSettingsSlice, type SettingsSlice } from './slices/settingsSlice';

export const useUserPrefsStore = create<ThemeSlice & SettingsSlice>()((...a) => ({
  ...createThemeSlice(...a),
  ...createSettingsSlice(...a),
}));
```

For most apps, prefer **multiple small stores** over one big sliced store. Coupling stores together via slices makes them harder to refactor.

## Resetting State (Logout)

```typescript
const initialState = {
  user: null,
  status: 'idle' as const,
  error: null,
};

export const useAuthStore = create<AuthState>()((set) => ({
  ...initialState,
  signIn: ...,
  signOut: () => set(initialState),
}));
```

For wiping ALL stores on logout (auth, prefs, cart, draft):

```typescript
// mobile/src/delivery/state/resetAllStores.ts
import { useAuthStore } from './authStore';
import { useCartStore } from './cartStore';
import { useDraftStore } from './draftStore';

export function resetAllStoresOnLogout() {
  useAuthStore.getState().reset?.();
  useCartStore.getState().reset?.();
  useDraftStore.getState().reset?.();
}
```

Each store exposes a `reset` method. Call from the logout flow + on user-switch.

## Subscribing to Selectors

```typescript
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

const useStore = create<State>()(
  subscribeWithSelector((set) => ({
    count: 0,
    increment: () => set((s) => ({ count: s.count + 1 })),
  }))
);

// Subscribe to changes of a specific slice:
const unsub = useStore.subscribe(
  (s) => s.count,
  (count) => console.log('count changed', count),
  { equalityFn: Object.is }
);
```

Useful for: bridging to non-React code (background sync triggers, analytics).

## Devtools

```typescript
import { devtools } from 'zustand/middleware';

export const useStore = create<State>()(
  devtools((set) => ({ ... }), { name: 'AppStore' })
);
```

Hooks into Redux DevTools Extension. RN: pair with Flipper.

## Testing Stores

```typescript
import { describe, it, expect } from 'vitest';
import { useAuthStore } from './authStore';

describe('authStore', () => {
  beforeEach(() => useAuthStore.getState().signOut());

  it('signs in successfully', async () => {
    await useAuthStore.getState().signIn('user@example.com', 'pw');
    const state = useAuthStore.getState();
    expect(state.user).toEqual(expect.objectContaining({ email: 'user@example.com' }));
    expect(state.status).toBe('authenticated');
  });
});
```

For component tests that depend on store state, set state directly:

```typescript
beforeEach(() => {
  useAuthStore.setState({ user: { id: 'usr_1', email: 'a@b.com' }, status: 'authenticated' });
});
```

## Anti-Patterns

1. **One mega-store** — violates separation of concerns; every change re-renders everything.
2. **Async fetch in store action** that duplicates a use case — call the use case from the store action, don't reimplement.
3. **Mutating state directly** — Zustand uses Object.assign internally; mutation breaks referential equality.
4. **`useStore()` (no selector)** — re-renders on every change.
5. **`getState()` in render** — bypasses subscription.
6. **Subscribing in render** — `useEffect` for subscriptions.
7. **Persisting auth tokens** — Keychain, never JSON.
8. **No store version** — schema change = corrupt persisted state on user devices.
9. **Async actions that do navigation** — couples store to router; pass a callback or use events.
10. **Storing functions in state** — they don't serialize; `partialize` strips them; behavior surprising.

## Source Material

- Zustand README — primary source: <https://github.com/pmndrs/zustand>
- TkDodo — *Working with Zustand*.
- React Native MMKV docs — for the storage adapter.
