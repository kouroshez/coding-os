import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/health_service.dart';

// Provider owns business logic; the screen only watches the AsyncValue.
final healthServiceProvider = Provider<HealthService>(
  (ref) => const HealthService(),
);

final healthStatusProvider = FutureProvider<String>((ref) async {
  final service = ref.watch(healthServiceProvider);
  return service.status();
});
