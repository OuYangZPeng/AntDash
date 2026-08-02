/// Centralized app configuration.
///
/// Switch [baseUrl] per environment. The value is used by [ApiClient] as the
/// default backend endpoint.
class AppConfig {
  /// Base URL of the AntDash backend API.
  ///
  /// Environments:
  /// - Local (physical device / iOS simulator):  http://127.0.0.1:8080
  /// - Android emulator:                          http://10.0.2.2:8080
  /// - Production (Tencent Cloud + HTTPS):        https://www.antdash.com
  ///
  /// NOTE: Android 9+ blocks cleartext HTTP by default. Use the HTTPS URL
  /// (or add `android:usesCleartextTraffic="true"` to the manifest) for a
  /// real device connecting to a plain-HTTP backend.
  static const String baseUrl = 'https://www.antdash.com';
}
