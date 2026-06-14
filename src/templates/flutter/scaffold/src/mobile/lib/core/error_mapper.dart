import 'dart:developer' as developer;

// The ONLY place that turns a thrown failure into a user-safe message.
// Screens render the returned string; full detail goes to the log, never
// the UI (no stack traces, no transport strings to the user).
String mapError(Object error, StackTrace stackTrace) {
  developer.log(
    'unhandled failure',
    name: '{{PROJECT_NAME}}',
    error: error,
    stackTrace: stackTrace,
  );
  if (error is FormatException) {
    return 'We received an unexpected response. Please try again.';
  }
  return 'Something went wrong. Please try again.';
}
