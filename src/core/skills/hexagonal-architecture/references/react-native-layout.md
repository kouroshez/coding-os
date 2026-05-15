# Hexagonal Layout — React Native Mobile Client

Yes, you really do want hexagonal in a mobile client — even more so when:

- The app calls **multiple backends** (your Go business core + your Python AI adapter), and you want one place to swap a transport without changing screens.
- The app needs **offline-first** behavior (queued mutations, sync-on-reconnect) — that logic IS your application layer, not a side-effect of TanStack Query options.
- You want to ship **Storybook screens with no real network**, drive by a fake gateway, and demo to designers without the backend running.
- You have business rules at all (e.g. "lesson is unlocked iff user has completed the previous one AND payment is current") — those rules belong in `domain/`, not in JSX.

Skip if your app is a thin wrapper over `fetch` and a few screens. Use it the moment a single screen needs to coordinate >1 use case.

## Folder Tree

```
mobile/
├── package.json
├── tsconfig.json
├── App.tsx                                 ← composition root: builds the graph, mounts navigation
├── src/
│   ├── domain/                             ← INNER — pure TypeScript, zero React/RN imports
│   │   ├── lesson/
│   │   │   ├── lesson.ts                   ← Lesson entity + invariants
│   │   │   ├── progress.ts                 ← value object: percent + state
│   │   │   ├── errors.ts
│   │   │   └── lesson.test.ts
│   │   ├── user/
│   │   │   ├── user.ts
│   │   │   └── subscription.ts
│   │   └── primitives/                     ← Branded types (UserID, ISODate)
│   │       ├── id.ts
│   │       └── result.ts                   ← Result<T, E> for ports that don't throw
│   │
│   ├── application/                        ← USE CASES + PORTS
│   │   ├── ports/
│   │   │   ├── lessonRepository.ts
│   │   │   ├── userRepository.ts
│   │   │   ├── aiAdapter.ts                ← talks to Python service (separate port from main backend)
│   │   │   ├── analyticsSink.ts
│   │   │   ├── secureStore.ts              ← Keychain/Keystore wrapper
│   │   │   ├── pushNotifier.ts
│   │   │   ├── clock.ts
│   │   │   ├── uuidGen.ts
│   │   │   └── unitOfWork.ts               ← optimistic-update + rollback wrapper
│   │   │
│   │   └── usecase/
│   │       ├── startLesson.ts              ← class with execute()
│   │       ├── startLesson.test.ts
│   │       ├── submitAnswer.ts
│   │       ├── recommendNextLesson.ts      ← calls aiAdapter port
│   │       └── syncOfflineQueue.ts
│   │
│   ├── infrastructure/                     ← OUTBOUND ADAPTERS
│   │   ├── http/
│   │   │   ├── apiClient.ts                ← axios/fetch wrapper, base URL, auth header injection
│   │   │   ├── lessonApiRepository.ts      ← implements LessonRepository
│   │   │   └── aiApiAdapter.ts             ← implements AIAdapter
│   │   ├── storage/
│   │   │   ├── secureStore.ts              ← @react-native-keychain wrapper
│   │   │   └── localCache.ts               ← MMKV adapter
│   │   ├── analytics/
│   │   │   └── posthogSink.ts              ← implements AnalyticsSink
│   │   ├── push/
│   │   │   └── notifeeNotifier.ts
│   │   └── system/
│   │       ├── systemClock.ts
│   │       └── randomUUID.ts
│   │
│   ├── delivery/                           ← INBOUND ADAPTERS — UI
│   │   ├── navigation/
│   │   │   ├── RootNavigator.tsx
│   │   │   ├── linking.ts                  ← deep-link → screen mapping
│   │   │   └── types.ts
│   │   ├── providers/
│   │   │   ├── DependencyProvider.tsx      ← React Context for use cases
│   │   │   └── useUseCase.ts               ← typed hook to retrieve a use case
│   │   ├── screens/
│   │   │   ├── lesson/
│   │   │   │   ├── LessonScreen.tsx        ← thin: hooks → useCase.execute → UI states
│   │   │   │   └── LessonScreen.stories.tsx
│   │   │   └── home/
│   │   │       └── HomeScreen.tsx
│   │   └── components/                     ← presentational, dumb, no use case calls
│   │       ├── Button.tsx
│   │       └── ProgressBar.tsx
│   │
│   └── fakes/                              ← in-memory adapters for tests + Storybook
│       ├── lessonRepository.ts
│       ├── aiAdapter.ts
│       └── clock.ts
└── __tests__/
    └── e2e/                                ← Detox / Maestro flows (very few)
```

## Domain — Branded Types Beat Primitive Obsession

```typescript
// src/domain/primitives/id.ts
export type Brand<T, B> = T & { readonly __brand: B };
export type UserID = Brand<string, 'UserID'>;
export type LessonID = Brand<string, 'LessonID'>;

export const UserID = {
  parse(raw: string): UserID {
    if (!/^usr_[a-z0-9]{12}$/.test(raw)) throw new Error(`invalid UserID: ${raw}`);
    return raw as UserID;
  },
};
```

```typescript
// src/domain/lesson/lesson.ts
import type { LessonID } from '../primitives/id';
import type { UserID } from '../primitives/id';
import { LessonNotUnlocked } from './errors';

export type LessonState = 'locked' | 'available' | 'in_progress' | 'completed';

export interface LessonProps {
  readonly id: LessonID;
  readonly title: string;
  readonly state: LessonState;
  readonly prerequisiteId: LessonID | null;
}

export class Lesson {
  private constructor(private readonly props: LessonProps) {}

  static fromProps(props: LessonProps): Lesson {
    return new Lesson(props);
  }

  get id(): LessonID { return this.props.id; }
  get title(): string { return this.props.title; }
  get state(): LessonState { return this.props.state; }
  get prerequisiteId(): LessonID | null { return this.props.prerequisiteId; }

  // Domain rule: a learner can start a lesson only if it is "available".
  start(_userId: UserID): Lesson {
    if (this.props.state !== 'available') {
      throw new LessonNotUnlocked(this.props.id, this.props.state);
    }
    return new Lesson({ ...this.props, state: 'in_progress' });
  }
}
```

## Ports — TypeScript Interfaces

```typescript
// src/application/ports/lessonRepository.ts
import type { Lesson } from '../../domain/lesson/lesson';
import type { LessonID, UserID } from '../../domain/primitives/id';

export interface LessonRepository {
  findById(id: LessonID): Promise<Lesson | null>;
  listForUser(userId: UserID): Promise<Lesson[]>;
  save(lesson: Lesson): Promise<void>;
}
```

```typescript
// src/application/ports/aiAdapter.ts — separate port for the Python service
import type { LessonID, UserID } from '../../domain/primitives/id';

export interface RecommendationRequest {
  readonly userId: UserID;
  readonly recentLessons: readonly LessonID[];
  readonly difficultyHint?: 'easier' | 'harder';
}

export interface RecommendationResult {
  readonly lessonId: LessonID;
  readonly confidence: number;        // 0..1
  readonly rationale: string;
}

export interface AIAdapter {
  recommendNextLesson(req: RecommendationRequest): Promise<RecommendationResult>;
}
```

Two separate ports for two separate backends. The use case does not know that one backend is Go and the other is Python; they are both "outbound dependencies the use case needs".

## Use Case — Plain TypeScript Class

```typescript
// src/application/usecase/recommendNextLesson.ts
import type { LessonRepository } from '../ports/lessonRepository';
import type { AIAdapter } from '../ports/aiAdapter';
import type { AnalyticsSink } from '../ports/analyticsSink';
import type { Clock } from '../ports/clock';
import type { UserID, LessonID } from '../../domain/primitives/id';

export interface RecommendNextLessonInput {
  readonly userId: UserID;
  readonly difficultyHint?: 'easier' | 'harder';
}

export interface RecommendNextLessonOutput {
  readonly lessonId: LessonID;
  readonly title: string;
  readonly rationale: string;
  readonly confidence: number;
}

export class RecommendNextLesson {
  constructor(
    private readonly lessons: LessonRepository,
    private readonly ai: AIAdapter,
    private readonly analytics: AnalyticsSink,
    private readonly clock: Clock,
  ) {}

  async execute(input: RecommendNextLessonInput): Promise<RecommendNextLessonOutput> {
    const all = await this.lessons.listForUser(input.userId);
    const recent = all
      .filter((l) => l.state === 'completed')
      .slice(-5)
      .map((l) => l.id);

    const result = await this.ai.recommendNextLesson({
      userId: input.userId,
      recentLessons: recent,
      difficultyHint: input.difficultyHint,
    });

    const recommended = await this.lessons.findById(result.lessonId);
    if (!recommended) {
      throw new Error(`AI returned unknown lesson: ${result.lessonId}`);
    }

    this.analytics.track('recommendation_shown', {
      lessonId: result.lessonId,
      confidence: result.confidence,
      timestamp: this.clock.nowISO(),
    });

    return {
      lessonId: result.lessonId,
      title: recommended.title,
      rationale: result.rationale,
      confidence: result.confidence,
    };
  }
}
```

## Composition Root — `App.tsx`

```typescript
// App.tsx
import { useMemo } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RootNavigator } from './src/delivery/navigation/RootNavigator';
import { DependencyProvider } from './src/delivery/providers/DependencyProvider';

import { ApiClient } from './src/infrastructure/http/apiClient';
import { LessonApiRepository } from './src/infrastructure/http/lessonApiRepository';
import { AiApiAdapter } from './src/infrastructure/http/aiApiAdapter';
import { PostHogAnalyticsSink } from './src/infrastructure/analytics/posthogSink';
import { KeychainSecureStore } from './src/infrastructure/storage/secureStore';
import { SystemClock } from './src/infrastructure/system/systemClock';
import { RandomUUID } from './src/infrastructure/system/randomUUID';

import { RecommendNextLesson } from './src/application/usecase/recommendNextLesson';
import { StartLesson } from './src/application/usecase/startLesson';
import { SubmitAnswer } from './src/application/usecase/submitAnswer';

export default function App() {
  const queryClient = useMemo(() => new QueryClient(), []);

  const useCases = useMemo(() => {
    const businessApi = new ApiClient({ baseURL: __DEV__ ? 'http://localhost:8080' : 'https://api.app.com' });
    const aiApi = new ApiClient({ baseURL: __DEV__ ? 'http://localhost:8000' : 'https://ai.app.com' });

    const lessons = new LessonApiRepository(businessApi);
    const ai = new AiApiAdapter(aiApi);
    const analytics = new PostHogAnalyticsSink();
    const secureStore = new KeychainSecureStore();
    const clock = new SystemClock();
    const uuid = new RandomUUID();

    return {
      recommendNextLesson: new RecommendNextLesson(lessons, ai, analytics, clock),
      startLesson: new StartLesson(lessons, analytics, clock),
      submitAnswer: new SubmitAnswer(lessons, ai, analytics, clock, uuid),
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <DependencyProvider value={useCases}>
        <NavigationContainer>
          <RootNavigator />
        </NavigationContainer>
      </DependencyProvider>
    </QueryClientProvider>
  );
}
```

## DependencyProvider — Type-safe Use Case Lookup

```typescript
// src/delivery/providers/DependencyProvider.tsx
import { createContext, useContext, type PropsWithChildren } from 'react';

import type { RecommendNextLesson } from '../../application/usecase/recommendNextLesson';
import type { StartLesson } from '../../application/usecase/startLesson';
import type { SubmitAnswer } from '../../application/usecase/submitAnswer';

export interface UseCases {
  readonly recommendNextLesson: RecommendNextLesson;
  readonly startLesson: StartLesson;
  readonly submitAnswer: SubmitAnswer;
}

const Ctx = createContext<UseCases | null>(null);

export function DependencyProvider({ value, children }: PropsWithChildren<{ value: UseCases }>) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUseCase<K extends keyof UseCases>(key: K): UseCases[K] {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useUseCase must be used inside <DependencyProvider>');
  return ctx[key];
}
```

## Screen — Thin Inbound Adapter

```typescript
// src/delivery/screens/home/HomeScreen.tsx
import { useQuery } from '@tanstack/react-query';
import { Text, View } from 'react-native';

import { useUseCase } from '../../providers/DependencyProvider';
import { useCurrentUserId } from '../../auth/useCurrentUserId';

export function HomeScreen() {
  const userId = useCurrentUserId();
  const recommend = useUseCase('recommendNextLesson');

  const { data, isLoading, error } = useQuery({
    queryKey: ['next-lesson', userId],
    queryFn: () => recommend.execute({ userId }),
  });

  if (isLoading) return <Text>Finding next lesson…</Text>;
  if (error) return <Text>Couldn’t load recommendation.</Text>;
  if (!data) return null;

  return (
    <View>
      <Text>Next: {data.title}</Text>
      <Text>Why: {data.rationale}</Text>
    </View>
  );
}
```

The screen does **not** know about Axios, AI service URLs, analytics SDKs, or auth tokens. It calls one method.

## Use Case Tests — No RN, No Network

```typescript
// src/application/usecase/recommendNextLesson.test.ts
import { describe, it, expect } from 'vitest';

import { RecommendNextLesson } from './recommendNextLesson';
import { InMemoryLessonRepository } from '../../fakes/lessonRepository';
import { FakeAIAdapter } from '../../fakes/aiAdapter';
import { NoopAnalyticsSink } from '../../fakes/analyticsSink';
import { FrozenClock } from '../../fakes/clock';

import { Lesson } from '../../domain/lesson/lesson';
import { LessonID, UserID } from '../../domain/primitives/id';

describe('RecommendNextLesson', () => {
  it('returns the lesson the AI suggests, decorated with title from the repo', async () => {
    const lessons = new InMemoryLessonRepository();
    const userId = UserID.parse('usr_aaaabbbbcccc');
    const lessonId = LessonID.parse('lsn_xxx');
    await lessons.save(
      Lesson.fromProps({ id: lessonId, title: 'Hexagons', state: 'available', prerequisiteId: null }),
    );

    const ai = new FakeAIAdapter({
      lessonId,
      confidence: 0.92,
      rationale: 'continues your last topic',
    });

    const uc = new RecommendNextLesson(
      lessons, ai, new NoopAnalyticsSink(),
      new FrozenClock('2026-04-26T12:00:00Z'),
    );

    const out = await uc.execute({ userId });

    expect(out.title).toBe('Hexagons');
    expect(out.confidence).toBe(0.92);
    expect(ai.callCount).toBe(1);
  });
});
```

## Storybook Wins

Because every screen takes its dependencies from context, you can render a screen in Storybook with `<DependencyProvider value={fakeUseCases}>` and demo any flow without a real backend. This is the underrated payoff of hexagonal in a mobile app.

## Common Mistakes

1. **Using TanStack Query's `mutationFn` AS the use case.** TanStack is a delivery concern (caching + retries + dedupe). The use case is what runs *inside* `mutationFn`.
2. **Putting Axios in the use case.** No. Use case takes a `LessonRepository`. The repository wraps Axios.
3. **Letting RN types into domain.** No `Image`, no `AsyncStorage`, no platform conditionals. If a domain entity needs an image URL, that's just a string.
4. **Singleton use cases at module top level.** Then tests can't swap them. Build inside `App.tsx` (or a factory called from there).
5. **Skipping fakes/.** Without an in-memory `LessonRepository`, your "use case tests" silently spin up Axios mocks and you lose half the value.

## Key References

- React Native 0.76+ docs (New Architecture is now default).
- React Navigation 7 deep linking: <https://reactnavigation.org/docs/deep-linking>
- TanStack Query as delivery layer: <https://tanstack.com/query/latest>
- "Mobile App Architecture in React Native" — Callstack engineering blog (2025+).
