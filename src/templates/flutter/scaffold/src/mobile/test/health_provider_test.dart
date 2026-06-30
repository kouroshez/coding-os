// Sample test for the Flutter scaffold — exercises the EXISTING health feature:
// the FutureProvider (state/) wired to HealthService (services/), and the error
// frame routed through the single error mapper (core/). Follows the flutter
// SKILL Testing section: providers tested via a ProviderContainer with the
// service overridden by a fake, the screen pumped inside a ProviderScope
// asserting the loading/error/data frames. No real network is bound.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../lib/screens/health_screen.dart';
import '../lib/services/health_service.dart';
import '../lib/state/health_provider.dart';

// A fake that returns a fixed status — no transport, fully deterministic.
class _FakeHealthService extends HealthService {
  const _FakeHealthService(this._status);

  final String _status;

  @override
  Future<String> status() async => _status;
}

// A fake that throws, so the screen's error frame is forced through mapError.
class _ThrowingHealthService extends HealthService {
  const _ThrowingHealthService();

  @override
  Future<String> status() async => throw const FormatException('bad payload');
}

void main() {
  group('healthStatusProvider', () {
    test('resolves to the value the injected service returns', () async {
      final container = ProviderContainer(
        overrides: [
          healthServiceProvider.overrideWithValue(
            const _FakeHealthService('ok'),
          ),
        ],
      );
      addTearDown(container.dispose);

      final result = await container.read(healthStatusProvider.future);

      expect(result, 'ok');
    });
  });

  group('HealthScreen', () {
    Widget pumpWith(HealthService service) => ProviderScope(
          overrides: [healthServiceProvider.overrideWithValue(service)],
          child: const MaterialApp(home: HealthScreen()),
        );

    testWidgets('shows the loading frame before the status resolves',
        (tester) async {
      await tester.pumpWidget(pumpWith(const _FakeHealthService('ok')));

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      await tester.pumpAndSettle();
    });

    testWidgets('renders the status once the service resolves',
        (tester) async {
      await tester.pumpWidget(pumpWith(const _FakeHealthService('ok')));
      await tester.pumpAndSettle();

      expect(find.text('status: ok'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('maps a thrown failure to a user-safe message, never the detail',
        (tester) async {
      await tester.pumpWidget(pumpWith(const _ThrowingHealthService()));
      await tester.pumpAndSettle();

      // The single error mapper turns FormatException into a safe string and
      // never leaks the thrown detail — the client-side equivalent of the
      // error envelope's "message safe to show end-users" rule.
      expect(
        find.text('We received an unexpected response. Please try again.'),
        findsOneWidget,
      );
      expect(find.textContaining('bad payload'), findsNothing);
    });
  });
}
