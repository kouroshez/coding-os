---
name: mobile-fundamentals
description: Cross-platform mobile concerns that apply regardless of framework — navigation patterns (stack/tab/drawer + deep links + universal links), offline-first sync (queue + retry + conflict resolution), push notifications (APNs + FCM end-to-end), background tasks, biometrics, app lifecycle, OTA updates, app store review prep. Use when adding any of these to a React Native, Flutter, or native iOS/Android app, or when reviewing a mobile feature where these concerns touch the design.
tier: layer
domain: [mobile]
last_reviewed: "2026-05-11"

---

# Mobile Fundamentals — Cross-Platform Concerns

The mobile-specific concerns that any framework (React Native, Flutter, native iOS/Android) has to address. Stack-agnostic patterns; concrete recipes target the project's React Native client.

## When to Use This Skill

- Adding navigation (stack / tab / drawer / modal) to a screen.
- Setting up deep links / universal links / app links.
- Implementing offline-first behavior (queue mutations, sync on reconnect).
- Adding push notifications (FCM + APNs).
- Wiring background tasks (sync, geofence, scheduled refresh).
- Gating sensitive ops with biometrics (Face ID / Touch ID / fingerprint).
- Handling app-state transitions (foreground / background / inactive).
- Planning OTA (over-the-air) updates and the rules around them.
- Preparing for App Store / Play Store review.

For RN-specific code patterns (component shapes, performance, native modules), see `react-native-patterns`.

## The Mobile Constraints That Don't Exist on Web

1. **Network is unreliable**. Cell signal drops; user goes through tunnels; offline is the steady state for some users.
2. **App can be killed at any moment**. iOS aggressively suspends; Android kills background processes.
3. **Multiple lifecycle states** beyond foreground/background — inactive, locked, swiped-away, terminated.
4. **Storage is shared with the OS** — running out of disk wedges your app.
5. **Battery is precious** — anything you do in background is metered.
6. **App store review** is a real release gate, not a CI step.
7. **Update install rate is slow** — 30 days to reach 90% adoption is normal.

Designing for these is the difference between "works in dev" and "actually ships".

## Navigation Patterns

### Picking the Right Container

| Pattern | Use when | Avoid when |
|---|---|---|
| **Stack** | Linear flows (sign-in → onboarding → home) | UI has 3+ peer destinations |
| **Tab** | 2–5 top-level destinations, accessible at all times | Flow has clear forward/back direction |
| **Drawer** | 6+ destinations, secondary navigation | <5 items (use tabs) |
| **Modal** | Self-contained task that closes back to where you were | Multi-step with deep nav |

**Hybrid is the norm**: tabs at the root, stacks within each tab, modals for "compose new ___" actions.

```
RootNavigator (Stack)
├── (Modal) Onboarding
├── (Modal) AuthFlow → SignIn / Register
└── MainTabs (Tab)
    ├── HomeStack (Stack)
    │   ├── Home
    │   ├── Lesson
    │   └── LessonComplete
    ├── ExploreStack (Stack)
    └── ProfileStack (Stack)
        ├── Profile
        └── Settings
```

### Deep Links — The Source of Truth

Every navigable screen must be addressable via a deep link. Pattern: `app://lessons/lsn_123` (or `https://app.com/lessons/lsn_123` for universal/app links).

```typescript
// mobile/src/delivery/navigation/linking.ts
import type { LinkingOptions } from '@react-navigation/native';
import type { RootStackParamList } from './types';

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [
    'app://',                        // custom scheme
    'https://app.com',               // universal link (iOS)
    'https://app.com',               // app link (Android)
  ],
  config: {
    screens: {
      MainTabs: {
        screens: {
          HomeStack: {
            screens: {
              Home: '',
              Lesson: 'lessons/:lessonId',
              LessonComplete: 'lessons/:lessonId/complete',
            },
          },
          ExploreStack: { screens: { Explore: 'explore' } },
          ProfileStack: { screens: { Profile: 'profile' } },
        },
      },
      AuthFlow: {
        screens: {
          MagicLinkConfirm: 'auth/magic/:token',
          PasswordReset:    'auth/reset/:token',
        },
      },
    },
  },
};
```

For the full universal-link / app-link / associated-domains setup (the OS-level configuration that makes `https://...` URLs open your app instead of Safari/Chrome), see [references/navigation-and-deep-links.md](references/navigation-and-deep-links.md).

### Magic Link / OTP Confirmation Routes

Critical: these MUST be deep links so a user clicking the email link from Mail.app on iOS lands in your app, not in Safari signed-out. Same for password reset, email verification, calendar invites.

If the user clicks on a device that doesn't have the app installed, fall back to a web confirmation page.

## Offline-First — The Real Pattern

"Offline-first" doesn't mean "works without network" — it means "writes don't fail just because the user's on the subway".

### The Three-Bucket Model

```
┌────────────────────────────────────────────────────────────┐
│  UI: optimistic state (immediate)                          │
│  ↓                                                          │
│  Local cache: source of truth for reads (durable, MMKV)    │
│  ↓                                                          │
│  Sync queue: mutations awaiting server confirmation        │
│  ↓                                                          │
│  Server (eventually consistent)                             │
└────────────────────────────────────────────────────────────┘
```

### Writes — Optimistic + Queue

```typescript
// mobile/src/application/usecase/markLessonComplete.ts
export class MarkLessonComplete {
  constructor(
    private readonly cache: LessonCache,
    private readonly queue: SyncQueue,
    private readonly clock: Clock,
  ) {}

  async execute(input: MarkLessonCompleteInput): Promise<void> {
    // 1. Update local cache immediately — UI re-renders.
    await this.cache.patch(input.lessonId, { state: 'completed', completed_at: this.clock.nowISO() });

    // 2. Enqueue server-side mutation. Returns immediately.
    await this.queue.enqueue({
      type: 'lesson.complete',
      payload: { lessonId: input.lessonId },
      idempotency_key: this.uuid.new(),
      created_at: this.clock.nowISO(),
    });
  }
}
```

The sync queue:

- Is durable (MMKV / SQLite). Survives app kill.
- Each entry has an `idempotency_key` — server-side dedup.
- Background worker drains FIFO when network is up.
- On 4xx (terminal failure), surface to UI: "this action couldn't sync — review".
- On 5xx / network error, exponential backoff retry up to N hours.

For the full implementation including conflict resolution (last-write-wins vs merge vs prompt-user), see [references/offline-sync.md](references/offline-sync.md).

### Reads — Cache + Revalidate

TanStack Query handles 90% of this:

```typescript
const { data } = useQuery({
  queryKey: ['lesson', id],
  queryFn: () => getLesson.execute({ lessonId: id }),
  staleTime: 60_000,      // serve from cache for 1 min, then revalidate
  gcTime: 24 * 3600_000,  // keep in cache 24h after unmount
  networkMode: 'offlineFirst',  // serve cache immediately, even when offline
});
```

For data that MUST be available offline (downloaded lessons, last 100 messages), pre-fetch on a sync schedule and persist.

## Push Notifications

### The Two-Token Dance

```
Device boots / app installs
  ↓
App requests notification permission (USER PROMPT)
  ↓ user grants
OS issues device token (APNs token / FCM token)
  ↓ FCM token (cross-platform via Firebase)
App POSTs to backend: { fcm_token, user_id, device_metadata }
  ↓
Backend stores in device_tokens table
  ↓
Backend sends notification → FCM/APNs → device → user sees it
```

### Permission Request Strategy

iOS + Android 13+ require explicit permission. Don't ask on app launch — ask in context (after the user does something that benefits from notifications: enrolls in a lesson, signs up for reminders).

```typescript
import notifee, { AuthorizationStatus } from '@notifee/react-native';

async function requestPushPermission(): Promise<boolean> {
  const settings = await notifee.requestPermission({
    sound: true, alert: true, badge: true,
  });
  return settings.authorizationStatus >= AuthorizationStatus.AUTHORIZED;
}
```

Show a "soft prompt" first (your own UI explaining why) — if user dismisses, don't waste the OS prompt.

### Notification Categories

iOS `UNNotificationCategoryOptions` + Android channels: group notifications by purpose (`lessons`, `social`, `transactional`). Users disable categories they don't want, keeping the ones they do.

### Background Handling

A notification can arrive when:

- App is foregrounded → show in-app banner (your choice).
- App is backgrounded → OS shows the notification.
- App is killed → OS shows the notification; tapping opens the app + delivers a launch intent.

For "tap notification → deep link to Lesson screen", parse the launch intent and navigate. See [references/navigation-and-deep-links.md](references/navigation-and-deep-links.md).

### Server-Side

```python
# Backend sends via FCM HTTP v1 API (not the deprecated legacy API).
# https://firebase.google.com/docs/cloud-messaging/migrate-v1

async def send_push(user_id: str, notif: Notification) -> None:
    tokens = await db.fetch("SELECT fcm_token FROM device_tokens WHERE user_id = $1", user_id)
    for row in tokens:
        try:
            await fcm.send_each([
                Message(
                    token=row["fcm_token"],
                    notification=Notification(title=notif.title, body=notif.body),
                    data={"deep_link": notif.deep_link},
                    apns=APNSConfig(payload=APNSPayload(aps=Aps(category=notif.category))),
                    android=AndroidConfig(notification=AndroidNotification(channel_id=notif.category)),
                ),
            ])
        except FcmError as exc:
            if exc.code in ("UNREGISTERED", "INVALID_ARGUMENT"):
                # Token is dead — clean up.
                await db.execute("DELETE FROM device_tokens WHERE fcm_token = $1", row["fcm_token"])
```

Token rotation: clean up dead tokens within 30 days (Apple TTL).

## Background Tasks

### What's Possible

| Platform | Mechanism | Constraints |
|---|---|---|
| iOS | `BGTaskScheduler` (background-fetch + processing) | OS decides when to run; once every few hours typical. |
| iOS | `URLSession` background config | For uploads/downloads; OS resumes on completion. |
| Android | `WorkManager` | Survives reboot; Doze mode delays unless expedited. |
| Android | Foreground Service | For long-running tasks (audio, location); shows persistent notification. |

### React Native

Use `react-native-background-fetch` (cross-platform wrapper around BGTaskScheduler + WorkManager). For specific needs:

- **Geofencing** → `react-native-background-geolocation` (battery-respecting; uses platform geofence APIs).
- **Periodic sync** → `BackgroundFetch.scheduleTask()` with 15-minute minimum.
- **One-shot deferred** → enqueue the work, schedule a wake.

NEVER assume a background task will run at exactly the time you ask. Treat scheduled times as "no sooner than" hints.

## Biometric Auth

Use for: app lock, sensitive ops (transfer money, change password, view 2FA codes).

```typescript
import * as Keychain from 'react-native-keychain';

async function unlockWithBiometrics(): Promise<string | null> {
  try {
    const creds = await Keychain.getGenericPassword({
      authenticationPrompt: { title: 'Unlock', subtitle: 'Use Face ID' },
    });
    return creds ? creds.password : null;
  } catch (e) {
    if (e.code === 'AuthenticationFailed' || e.code === 'UserCanceled') {
      return null;
    }
    throw e;
  }
}
```

Rules:

- **Always offer a passcode fallback** — user fingers wet, mask on, etc. Use `Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE`.
- **Re-prompt on backgrounding > N seconds** — typical bank-app behavior is 30-60 seconds before re-prompting.
- **Detect biometric change** — `Keychain.canImplyAuthentication` + on-mismatch wipe stored creds (some other Face ID enrolled).
- **NEVER use biometrics as proof of identity to the server** — they're a local UX gate. The server still needs a password / token for actual auth.

## App Lifecycle

### React Native AppState Events

```typescript
import { AppState, type AppStateStatus } from 'react-native';

useEffect(() => {
  const sub = AppState.addEventListener('change', (state: AppStateStatus) => {
    if (state === 'active') resumeWork();
    if (state === 'background') pauseWork();
    if (state === 'inactive') {/* iOS-only: control center, app switcher */}
  });
  return () => sub.remove();
}, [resumeWork, pauseWork]);
```

Common patterns:

- **Resume**: refetch stale data, reconnect WebSocket, re-prompt biometric if locked.
- **Background**: pause polling, flush analytics, cancel non-essential network.
- **Killed**: anything you didn't persist is gone. Persist before backgrounding for critical state.

### Dealing with the App-Switcher Screenshot

iOS takes a screenshot of your app for the app-switcher. If you display sensitive data (banking, medical), blur or hide it on `inactive`.

```typescript
const [redacted, setRedacted] = useState(false);
useEffect(() => {
  const sub = AppState.addEventListener('change', (s) => {
    setRedacted(s !== 'active');
  });
  return () => sub.remove();
}, []);

return redacted ? <RedactedView /> : <RealView />;
```

## OTA Updates

When useful: bug fixes, copy changes, layout tweaks. Avoid for: anything that changes JS<>native bridge contracts, native dependencies, OS-permission usage.

For RN: `expo-updates` (works in bare RN since SDK 49). Microsoft App Center sunset in 2024 — don't migrate to it.

Apple/Google policies (2026):

- **Apple**: OTA allowed for RN as long as you don't substantially change app function. Don't push OTA that adds new features unrelated to the reviewed version.
- **Google**: Permits any code change that doesn't add new permissions / collect new data.

Treat OTA as a hotfix mechanism, not a feature-delivery mechanism. Schedule a real store release every 2-4 weeks.

## App Store / Play Store Review

### Common Rejection Reasons

1. **No way to delete account** — Apple requires in-app account deletion (Guideline 5.1.1(v)).
2. **Login screen with no "guest" / "skip"** — Apple wants apps usable without account where possible.
3. **Missing usage descriptions** — every permission needs an `Info.plist` `NSXxxUsageDescription` string explaining WHY.
4. **Crashes on launch** — they will reject.
5. **Web view that's just your website** — Apple Guideline 4.2; needs native value-add.
6. **Sign In with Apple missing** — required if you offer any third-party login (Google, Facebook, etc.) on iOS.
7. **In-app purchase of digital goods via your own payment** — must use Apple IAP for iOS.
8. **Targeting children without COPPA flow** — needs explicit handling.

### Pre-Submission Checklist

See [assets/mobile-launch-checklist.md](assets/mobile-launch-checklist.md).

## Common Mobile Mistakes

1. **Treating offline as an exception case** — should be steady state.
2. **No idempotency on mutations** — retries become double-actions.
3. **Sync queue without deduplication** — same mutation enqueued N times on N retries.
4. **Push token never refreshed** — tokens rotate; if you never re-register, sends silently fail.
5. **Permission asked on launch** — high reject rate; ask in context.
6. **No notification categories** — user's only choice is "all on" or "all off".
7. **No Sign In with Apple** — App Store rejection.
8. **No "delete my account"** — App Store rejection.
9. **Long app launch** — anything > 2s feels broken; defer non-essential init.
10. **No crash reporting** with sourcemaps/dSYM uploaded — crashes show as obfuscated stack frames forever.
11. **No analytics consent flow** in EU/UK — GDPR violation.
12. **Hardcoded API URLs** — staging build hits prod.

## Source Material

- Apple — *Human Interface Guidelines* (current 2025 update for iOS 18).
- Google — *Material Design 3* + *Android API Guidelines*.
- React Navigation 7 docs — navigation depth.
- Firebase Cloud Messaging HTTP v1 API docs.
- `notifee` documentation — best library for cross-platform local + remote notifications.
- Apple Developer — *App Store Review Guidelines* (current).
- Google Play — *Developer Program Policies* (current).
- *Designing Mobile Apps* — Luke Wroblewski, design principles still apply.
