# Navigation + Deep Links — Implementation Reference

The OS-level setup that makes `https://app.com/lessons/xyz` open your app, plus the in-app routing that handles it.

## Universal Links (iOS) — Setup

### 1. Apple App Site Association File

Host at `https://app.com/.well-known/apple-app-site-association` (no extension). MUST be served over HTTPS, MUST be `Content-Type: application/json` (or no content type — Apple is flexible), MUST NOT redirect.

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID.com.app.bundle"],
        "components": [
          {
            "/": "/lessons/*",
            "comment": "Opens lesson detail"
          },
          {
            "/": "/auth/magic/*",
            "comment": "Magic-link sign-in"
          },
          {
            "/": "/profile",
            "exclude": false
          }
        ]
      }
    ]
  },
  "webcredentials": {
    "apps": ["TEAMID.com.app.bundle"]
  }
}
```

Verify with `curl -I https://app.com/.well-known/apple-app-site-association` — Apple's CDN crawls this on first install and caches; updates take ~24h to propagate.

### 2. Xcode Configuration

In your target's "Signing & Capabilities":

- Add capability **Associated Domains**.
- Add: `applinks:app.com`
- Add: `webcredentials:app.com` (for password autofill).

### 3. Verify

```bash
# On a real device (simulator doesn't reliably test universal links):
xcrun simctl openurl booted "https://app.com/lessons/lsn_123"
# Or just tap a link in Mail / Notes / Safari.
```

If Safari opens instead of your app: AASA file is malformed, capability missing, or first-install crawl pending.

## Android App Links — Setup

### 1. Asset Links File

Host at `https://app.com/.well-known/assetlinks.json`. Same constraints (HTTPS, no redirect).

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.app",
    "sha256_cert_fingerprints": [
      "AB:CD:EF:..."
    ]
  }
}]
```

Get the SHA-256 fingerprint:

```bash
keytool -list -v -keystore release.keystore -alias my-key
# Copy "SHA256:" line from output.
```

For Play App Signing (recommended), get the upload key + the Play-managed signing key fingerprints (both required) from Play Console > Setup > App integrity.

### 2. Manifest

```xml
<!-- mobile/android/app/src/main/AndroidManifest.xml -->
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="app.com" />
    </intent-filter>

    <!-- Custom scheme fallback -->
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="app" />
    </intent-filter>
</activity>
```

`autoVerify="true"` triggers verification of the assetlinks.json on install. Confirm via:

```bash
adb shell pm get-app-links com.app
# State: "verified" if good.
```

## Custom Scheme Fallback

Both platforms also accept `app://lessons/lsn_123`. Used for:

- Local notification taps (don't need a real URL).
- Email/SMS where you control the link.
- Test environments without HTTPS setup.

Don't rely on custom schemes for cross-app links — universal/app links beat them in every scenario where they work.

## React Navigation Linking Config

```typescript
// mobile/src/delivery/navigation/linking.ts
import type { LinkingOptions } from '@react-navigation/native';
import * as Linking from 'expo-linking';   // or react-native's Linking module
import messaging from '@react-native-firebase/messaging';

import type { RootStackParamList } from './types';

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [
    'app://',
    'https://app.com',
    'https://www.app.com',
  ],
  async getInitialURL() {
    // 1. Cold-start from a deep-link tap.
    const url = await Linking.getInitialURL();
    if (url) return url;

    // 2. Cold-start from a notification tap (FCM v1).
    const message = await messaging().getInitialNotification();
    if (message?.data?.deep_link) return String(message.data.deep_link);

    return null;
  },
  subscribe(listener) {
    // 1. Live deep-link events while app is running.
    const linkSub = Linking.addEventListener('url', ({ url }) => listener(url));

    // 2. Notification tap while app is backgrounded.
    const notifSub = messaging().onNotificationOpenedApp((message) => {
      if (message?.data?.deep_link) listener(String(message.data.deep_link));
    });

    return () => {
      linkSub.remove();
      notifSub();
    };
  },
  config: {
    initialRouteName: 'MainTabs',
    screens: {
      MainTabs: {
        path: '',
        screens: {
          HomeStack: {
            path: 'home',
            screens: {
              Home: '',
              Lesson: {
                path: 'lessons/:lessonId',
                parse: { lessonId: String },
              },
            },
          },
          ProfileStack: {
            path: 'profile',
            screens: { Profile: '' },
          },
        },
      },
      AuthFlow: {
        path: 'auth',
        screens: {
          MagicLinkConfirm: 'magic/:token',
          PasswordReset: 'reset/:token',
        },
      },
      NotFound: '*',
    },
  },
};
```

Key points:

- `initialRouteName` ensures the back stack is sane after a deep-link cold start (back from Lesson goes to Home, not exits).
- `parse` for type coercion (numeric IDs, booleans).
- A `NotFound: '*'` catch-all screen makes broken links survivable.

## Auth-Required Deep Links

Deep links can target screens behind auth. Pattern:

```typescript
// mobile/src/delivery/navigation/AuthGate.tsx
export function AuthGate({ children }: PropsWithChildren) {
  const { isAuthenticated, isResolving } = useAuth();
  const navigation = useNavigation();
  const route = useRoute();

  useEffect(() => {
    if (isResolving) return;
    if (!isAuthenticated && requiresAuth(route.name)) {
      // Stash the intended destination, route to sign-in.
      pendingNavigation.set(route.name, route.params);
      navigation.reset({
        index: 0,
        routes: [{ name: 'AuthFlow', params: { screen: 'SignIn' } }],
      });
    }
  }, [isAuthenticated, isResolving, route]);

  if (isResolving) return <SplashScreen />;
  return children;
}

// On successful sign-in:
function onSignInComplete() {
  const stash = pendingNavigation.consume();
  if (stash) {
    navigation.reset({
      index: 1,
      routes: [
        { name: 'MainTabs' },
        { name: stash.name, params: stash.params },
      ],
    });
  } else {
    navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] });
  }
}
```

## Modal Routes

Modal screens (compose, settings, paywall) are best as separate stacks with `presentation: 'modal'`:

```typescript
<Stack.Navigator>
  <Stack.Screen name="MainTabs" component={MainTabs} />
  <Stack.Group screenOptions={{ presentation: 'modal' }}>
    <Stack.Screen name="ComposeMessage" component={ComposeScreen} />
    <Stack.Screen name="Paywall"        component={PaywallScreen} />
  </Stack.Group>
</Stack.Navigator>
```

Modal routes are still deep-linkable (`/compose`, `/upgrade`).

## Tab Bar — When to Hide

For iOS-style modal flows where the user is "in" something, hide the tab bar:

```typescript
<Stack.Screen
  name="LessonPlayer"
  component={LessonPlayer}
  options={{ tabBarStyle: { display: 'none' } }}
/>
```

But: tab bar disappearing AND reappearing causes layout shift. For long flows, prefer modal presentation that covers the tabs entirely.

## Back Behavior — Be Explicit

### Android Hardware Back Button

```typescript
import { useFocusEffect } from '@react-navigation/native';
import { BackHandler } from 'react-native';

useFocusEffect(useCallback(() => {
  const onBackPress = () => {
    if (hasUnsavedChanges) {
      promptDiscardOrSave();
      return true;  // we handled it; don't navigate back
    }
    return false;  // let default handler navigate back
  };
  const sub = BackHandler.addEventListener('hardwareBackPress', onBackPress);
  return () => sub.remove();
}, [hasUnsavedChanges]));
```

### Beforeunload Warning

```typescript
useEffect(() => {
  return navigation.addListener('beforeRemove', (e) => {
    if (!hasUnsavedChanges) return;
    e.preventDefault();
    Alert.alert('Discard changes?', '', [
      { text: 'Stay', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: () => navigation.dispatch(e.data.action) },
    ]);
  });
}, [navigation, hasUnsavedChanges]);
```

## Common Navigation Mistakes

1. **No deep link config** — magic-link emails open Safari, not your app.
2. **Stack.Screen `getInitialURL` not handling notification taps** — push-tap launches go to home, not the screen.
3. **Hardcoded screen names** — typos at runtime, no autocomplete. Use the typed `RootStackParamList`.
4. **`navigation.navigate('Home')` for "go home"** — pushes Home onto stack. Use `navigation.popToTop()` or `navigation.reset(...)`.
5. **Modal that doesn't dismiss properly** — `presentation: 'modal'` + `goBack()` works; pushed Stack screens trying to "modal close" don't.
6. **No NotFound route** — typo in deep link → app crashes.
7. **`useNavigation()` without typed generic** — `nav.navigate('LesonComplete')` (typo) compiles, fails at runtime. Always `useNavigation<NativeStackNavigationProp<RootStackParamList>>()`.
8. **Auto-verify off on Android** — links open in browser even when app is installed.
9. **Universal link from email opens browser tab AND app** — old AASA cached; force re-verify by reinstalling or `xcrun simctl openurl`.
10. **`linking.config.initialRouteName` missing** — back from deep-linked screen exits app instead of going home.

## Source Material

- React Navigation 7 — *Configuring links*: <https://reactnavigation.org/docs/configuring-links>
- Apple — *Allowing Apps and Websites to Link to Your Content*.
- Google — *Verify Android App Links*.
- Branch.io / AppsFlyer / Adjust — deferred deep linking (cold install + attribution); only if you need install attribution.
