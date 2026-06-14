import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_mapper.dart';
import '../state/health_provider.dart';

// A ConsumerWidget that renders the three states of an async value.
class HealthScreen extends ConsumerWidget {
  const HealthScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(healthStatusProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('{{PROJECT_NAME}}')),
      body: Center(
        child: status.when(
          loading: () => const CircularProgressIndicator(),
          error: (error, stackTrace) => Semantics(
            label: 'Health check failed',
            child: Text(mapError(error, stackTrace)),
          ),
          data: (value) => Semantics(
            header: true,
            label: 'Health status $value',
            child: Text('status: $value'),
          ),
        ),
      ),
    );
  }
}
