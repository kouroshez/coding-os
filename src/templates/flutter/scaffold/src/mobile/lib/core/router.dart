import 'package:go_router/go_router.dart';

import '../screens/health_screen.dart';

// The single declarative router — widgets never push raw routes.
final GoRouter appRouter = GoRouter(
  routes: <RouteBase>[
    GoRoute(
      path: '/',
      builder: (context, state) => const HealthScreen(),
    ),
  ],
);
