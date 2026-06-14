// Transport lives here — screens never call this directly, only via a provider.
// Returns a domain value or throws a typed failure for the error mapper.
class HealthService {
  const HealthService();

  Future<String> status() async {
    // Stand-in for a real health check (HTTP / platform channel).
    await Future<void>.delayed(const Duration(milliseconds: 50));
    return 'ok';
  }
}
